#!/usr/bin/env python3
"""
SDN Learning Switch - Custom Mininet Topology
4 hosts connected to a single OpenFlow switch
"""

from mininet.net import Mininet
from mininet.node import Controller, RemoteController, OVSKernelSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel, info
from mininet.link import TCLink

def create_topology():
    """Create and run the SDN topology."""
    net = Mininet(
        controller=RemoteController,
        switch=OVSKernelSwitch,
        link=TCLink,
        autoSetMacs=True
    )

    info('*** Adding controller (Ryu running on localhost:6633)\n')
    c0 = net.addController('c0', controller=RemoteController,
                            ip='127.0.0.1', port=6633)

    info('*** Adding switch\n')
    s1 = net.addSwitch('s1', protocols='OpenFlow13')

    info('*** Adding hosts\n')
    h1 = net.addHost('h1', ip='10.0.0.1/24', mac='00:00:00:00:00:01')
    h2 = net.addHost('h2', ip='10.0.0.2/24', mac='00:00:00:00:00:02')
    h3 = net.addHost('h3', ip='10.0.0.3/24', mac='00:00:00:00:00:03')
    h4 = net.addHost('h4', ip='10.0.0.4/24', mac='00:00:00:00:00:04')

    info('*** Creating links\n')
    net.addLink(h1, s1, bw=10, delay='5ms')
    net.addLink(h2, s1, bw=10, delay='5ms')
    net.addLink(h3, s1, bw=10, delay='5ms')
    net.addLink(h4, s1, bw=10, delay='5ms')

    info('*** Starting network\n')
    net.start()

    info('*** Network is ready. Use CLI to test.\n')
    info('*** Try: pingall, h1 ping h2, h1 iperf h2\n')
    CLI(net)

    info('*** Stopping network\n')
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    create_topology()