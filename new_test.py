import os
import yaml
import networkx as nx
import matplotlib.pyplot as plt
from collections import defaultdict
import matplotlib.colors as mcolors

# ==============================
# STEP 1: Load Topology Data
# ==============================
with open('topology.yaml', 'r') as file:
    topology = yaml.safe_load(file)

# Build switch connections from topology data
switch_connections = {}
for link in topology['links']:
    switch_connections[(link['source'], link['source_port'])] = (link['destination'], link['destination_port'])
    switch_connections[(link['destination'], link['destination_port'])] = (link['source'], link['source_port'])
print("switch_connections", switch_connections)
# ==============================
# STEP 2: Parse MAC Tables
# ==============================
mac_tables = defaultdict(list)
for filename in os.listdir():
    if filename.endswith('.txt') and filename != 'topology.yml':
        switch_name = filename.replace('.txt', '')
        with open(filename, 'r') as f:
            for line in f:
                if '(port:' in line:
                    parts = line.strip().split()
                    mac_address = parts[0]
                    port = parts[2].strip(')')
                    vlan = parts[4]
                    # Append all occurrences of the MAC address properly
                    mac_tables[mac_address].append((switch_name, port, vlan))

# ==============================
# STEP 3: Detect VLAN Leaks and Remove Non-Access Ports
# ==============================
leaking_switches = []
device_locations = defaultdict(list)  # Now this holds a list of all locations
print("mac_tables", mac_tables.items())
for mac, locations in mac_tables.items():
    print("locations", locations)
    print("mac", mac)
    new_locations = []
    # Check if every VLAN is consistent across all locations
    if len(locations) > 1:
        all_same_vlan = all(loc[2] == locations[0][2] for loc in locations)
        if all_same_vlan:
            print(f"All the same: {locations[0][2]}")
        else:
            #print("VLANs are not the same across locations")
            for switch_name, port, vlan in locations:
                # Check if the switch-port pair is in switch_connections
                #print(f"Checking switch-port pair ({switch_name}, {port})") 
                if (switch_name, int(port)) in switch_connections:
                    #print(f"Switch-port pair ({switch_name}, {port}) is present in switch_connections")
                    leaking_switches.append(switch_name)
                else:
                    new_locations.append((switch_name, port, vlan))        
                    #print(f"Switch-port pair ({switch_name}, {port}) is NOT present in switch_connections")
    else:
        new_locations.append(locations[0][0],locations[0][1],locations[0][2])         
    # Now we check each location, and remove non-access ports (those leading to other switches)
    device_locations[mac] = new_locations
'''    for switch_name, port, vlan in locations:
        if (switch_name, port) in switch_connections:
            # Port leading to another switch (trunk port) -> Remove it
            if switch_name not in leaking_switches:  # Only mark switch as leaking if it has more than 1 VLAN
                continue
        new_locations.append((switch_name, port, vlan))'''

    # Store only filtered locations

print("device_locations", device_locations)
print("leaking_switches", leaking_switches)
# ==============================
# STEP 4: Build Graph Topology
# ==============================
G = nx.Graph()

# Add switch nodes, mark them as red if they are leaking VLANs
for switch in topology['switches']:
    color = 'red' if switch['name'] in leaking_switches else 'lightblue'
    G.add_node(switch['name'], type='switch', color=color)

# Add links between switches
for (src, src_port), (dst, dst_port) in switch_connections.items():
    G.add_edge(src, dst, label=f'{src_port} <-> {dst_port}', color='gray')

# Add device nodes and edges to their primary switch
color_keys = list(mcolors.CSS4_COLORS.keys())
for mac, locations in device_locations.items():
    print("locations", locations)
    for switch, port, vlan in locations:
        # If it's connected to a trunk port, skip visualization
        if (switch, port) in switch_connections:  # If it's a trunk port, skip the device visualization
            continue
        G.add_node(mac, type='device')
        color = mcolors.CSS4_COLORS[color_keys[(int(vlan) * 7) % len(color_keys)]]
        G.add_edge(switch, mac, label=f'Port {port} (VLAN {vlan})', color=color)

# ==============================
# STEP 5: Visualize the Network
# ==============================
vlans = {vlan for locs in device_locations.values() for _, _, vlan in locs}
vlan_colors = {vlan: mcolors.CSS4_COLORS[color_keys[(int(vlan) * 7) % len(color_keys)]] for vlan in vlans}

# Define colors for each node
node_colors = [G.nodes[n]['color'] if 'color' in G.nodes[n] else 'gray' for n in G.nodes()]

# Draw the network
pos = nx.spring_layout(G)
plt.figure(figsize=(10, 8))
edge_colors = [G[u][v]['color'] for u, v in G.edges()]
nx.draw(G, pos, with_labels=True, node_color=node_colors, edge_color=edge_colors, node_size=500)
edge_labels = nx.get_edge_attributes(G, 'label')
nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels)

# Add legend for VLANs
for vlan, color in vlan_colors.items():
    plt.scatter([], [], c=[color], label=f'VLAN {vlan}')
plt.legend(loc='upper left', title='VLANs')
plt.title('Network Topology with VLAN Leaking Detection')
plt.show()
