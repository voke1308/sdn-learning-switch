# SDN Learning Switch Controller

## Problem Statement
Implement a controller that mimics a learning switch by dynamically learning 
MAC addresses and installing forwarding rules using OpenFlow 1.3 on Mininet.

## Tools & Technologies
- **Mininet** — Network emulation
- **Ryu Controller** — OpenFlow 1.3 SDN controller
- **OVS (Open vSwitch)** — Software switch
- **iperf / ping / Wireshark** — Testing and validation

## Topology
4 hosts (h1–h4) connected to a single OVS switch (s1), 
managed by a remote Ryu controller.

## Setup & Execution

### Prerequisites
```bash
sudo apt install mininet wireshark iperf -y
pip install ryu
```

### Run
```bash
# Terminal 1: Start Ryu controller
ryu-manager --verbose learning_switch.py

# Terminal 2: Start Mininet
sudo python3 topology.py
```

## How It Works
1. Switch connects → controller installs table-miss rule
2. Unknown packet → sent to controller (packet_in)
3. Controller learns: source MAC → port
4. If dst MAC known → install flow rule + forward
5. If dst MAC unknown → flood all ports

## Test Scenarios

### Scenario 1: Ping Test
mininet> pingall
mininet> h1 ping -c 5 h2
mininet> sh ovs-ofctl dump-flows s1

### Scenario 2: iperf Throughput
mininet> h2 iperf -s &
mininet> h1 iperf -c 10.0.0.2

## Expected Output
- First ping: flooded, MAC learned, flow installed
- Second ping: forwarded directly by switch (no packet_in)
- Flow table shows installed rules with idle_timeout=30

## Screenshots
[Add your screenshots here]

## References
- Ryu documentation: https://ryu.readthedocs.io
- Mininet walkthrough: http://mininet.org/walkthrough/
- OpenFlow 1.3 spec: https://opennetworking.org/wp-content/uploads/2014/10/openflow-spec-v1.3.0.pdf
