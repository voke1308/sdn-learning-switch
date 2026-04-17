#!/usr/bin/env python3
"""
SDN Learning Switch Controller - Ryu OpenFlow 1.3
-------------------------------------------------------
Implements MAC address learning and dynamic flow installation.
- On packet_in: learn source MAC → port mapping
- If destination MAC known: install a flow rule and forward
- If unknown: flood to all ports
"""

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types, ipv4, icmp, tcp, udp
import logging
import time

class LearningSwitch(app_manager.RyuApp):
    """
    A learning switch controller using OpenFlow 1.3.
    Learns MAC-to-port mappings and installs unicast flow rules.
    """
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(LearningSwitch, self).__init__(*args, **kwargs)
        
        # MAC address table: {dpid: {mac: port}}
        self.mac_to_port = {}
        
        # Statistics tracking
        self.packet_in_count = 0
        self.flow_installed_count = 0
        self.flood_count = 0
        
        self.logger.setLevel(logging.INFO)
        self.logger.info("=" * 60)
        self.logger.info("  SDN Learning Switch Controller Started")
        self.logger.info("  OpenFlow 1.3 | Ryu Framework")
        self.logger.info("=" * 60)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """
        Called when a switch connects.
        Installs a table-miss flow entry to send unknown packets to controller.
        """
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        dpid = datapath.id

        self.logger.info("[+] Switch connected: DPID=%s", dpid)

        # Install table-miss entry: match ALL, send to controller
        match = parser.OFPMatch()  # matches everything
        actions = [parser.OFPActionOutput(
            ofproto.OFPP_CONTROLLER,
            ofproto.OFPCML_NO_BUFFER
        )]
        self._add_flow(datapath, priority=0, match=match, actions=actions)
        self.logger.info("[+] Table-miss flow entry installed on DPID=%s", dpid)

    def _add_flow(self, datapath, priority, match, actions,
                  idle_timeout=0, hard_timeout=0, buffer_id=None):
        """
        Helper: Install a flow rule on the switch.
        
        Args:
            datapath: Switch object
            priority: Flow rule priority (higher = matched first)
            match: OFPMatch object defining what to match
            actions: List of actions to perform
            idle_timeout: Seconds of inactivity before deletion (0 = permanent)
            hard_timeout: Absolute seconds before deletion (0 = permanent)
            buffer_id: Packet buffer ID (if packet is buffered on switch)
        """
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(
            ofproto.OFPIT_APPLY_ACTIONS, actions
        )]

        if buffer_id:
            mod = parser.OFPFlowMod(
                datapath=datapath,
                buffer_id=buffer_id,
                priority=priority,
                match=match,
                instructions=inst,
                idle_timeout=idle_timeout,
                hard_timeout=hard_timeout
            )
        else:
            mod = parser.OFPFlowMod(
                datapath=datapath,
                priority=priority,
                match=match,
                instructions=inst,
                idle_timeout=idle_timeout,
                hard_timeout=hard_timeout
            )

        datapath.send_msg(mod)
        self.flow_installed_count += 1
        self.logger.info(
            "[FLOW] Rule installed | DPID=%s | Priority=%d | Timeouts(idle=%d, hard=%d)",
            datapath.id, priority, idle_timeout, hard_timeout
        )

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        """
        Core learning logic. Called for every unknown packet.
        
        Steps:
        1. Parse the incoming packet
        2. Learn source MAC → in_port mapping
        3. Look up destination MAC
        4. If known: install flow rule + forward
        5. If unknown: flood
        """
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']
        dpid = datapath.id

        self.packet_in_count += 1

        # Parse the raw packet
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        # Ignore LLDP (Link Layer Discovery Protocol)
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        src_mac = eth.src
        dst_mac = eth.dst

        # ── Step 1: Initialize MAC table for this switch ──
        self.mac_to_port.setdefault(dpid, {})

        # ── Step 2: LEARN — record source MAC → in_port ──
        if src_mac not in self.mac_to_port[dpid]:
            self.logger.info(
                "[LEARN] DPID=%s | MAC=%s → Port=%s", dpid, src_mac, in_port
            )
        self.mac_to_port[dpid][src_mac] = in_port
        
        # ── Step 2.5: Handle broadcast/multicast destinations early ──
        is_broadcast = (dst_mac == 'ff:ff:ff:ff:ff:ff')
        is_multicast = (dst_mac.startswith('33:33') or 
                        dst_mac.startswith('01:00:5e') or
                        dst_mac.startswith('01:80:c2'))

        if is_broadcast or is_multicast:
            # Always flood these, never try to install a flow rule for them
            out_port = ofproto.OFPP_FLOOD
            self.flood_count += 1
            self.logger.info(
                "[FLOOD] DPID=%s | %s → %s (broadcast/multicast) | Floods=%d",
                dpid, src_mac, dst_mac, self.flood_count
            )
            actions = [parser.OFPActionOutput(out_port)]
            out = parser.OFPPacketOut(
                datapath=datapath,
                buffer_id=ofproto.OFP_NO_BUFFER,
                in_port=in_port,
                actions=actions,
                data=msg.data
            )
            datapath.send_msg(out)
            return

        # ── Step 3: FORWARD — decide output port ──
        if dst_mac in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst_mac]
            self.logger.info(
                "[FORWARD] DPID=%s | %s → %s | Port %s → %s",
                dpid, src_mac, dst_mac, in_port, out_port
            )

            # ── Step 4: Install a flow rule for future packets ──
            actions = [parser.OFPActionOutput(out_port)]
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst_mac, eth_src=src_mac)

            self._add_flow(datapath, priority=1, match=match,
                           actions=actions, idle_timeout=30,
                           hard_timeout=120)
        else:
            # ── Step 5: FLOOD — destination unknown ──
            out_port = ofproto.OFPP_FLOOD
            self.flood_count += 1
            self.logger.info(
                "[FLOOD] DPID=%s | %s → %s (unknown dst) | Floods=%d",
                dpid, src_mac, dst_mac, self.flood_count
            )
            actions = [parser.OFPActionOutput(out_port)]

        # Send the current packet out
       
        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data
        )
        datapath.send_msg(out)

    def print_mac_table(self):
        """Utility: Print current MAC address table."""
        self.logger.info("=" * 50)
        self.logger.info("Current MAC Address Table:")
        for dpid, mac_table in self.mac_to_port.items():
            self.logger.info("  Switch DPID: %s", dpid)
            for mac, port in mac_table.items():
                self.logger.info("    MAC: %s → Port: %s", mac, port)
        self.logger.info("Stats: packet_in=%d, flows_installed=%d, floods=%d",
                         self.packet_in_count, self.flow_installed_count, self.flood_count)
        self.logger.info("=" * 50)