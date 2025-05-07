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
leaking_switches = set()
device_locations = defaultdict(list)  # Now this holds a list of all locations
print("mac_tables", mac_tables.items())
for mac, locations in list(mac_tables.items()): # Use list(mac_tables.items()) if you plan to modify mac_tables inside loop, though here we populate device_locations
    print(f"\nProcessing MAC: {mac}, Original Locations: {locations}")
    
    processed_locations_for_mac = [] # To store locations that are deemed access ports for this MAC

    if not locations: # Should not happen if mac_tables is built correctly
        continue

    if len(locations) == 1:
        # If MAC is seen in only one location, assume it's an access port
        print(f"  MAC {mac} seen in a single location. Treating as access port.")
        processed_locations_for_mac = locations
    else: # MAC seen in multiple locations
        # Check if VLAN is consistent across all locations for this MAC
        first_vlan = locations[0][2]
        # Corrected 'all_same' check: iterate through each location's VLAN
        all_same_vlan = all(loc[2] == first_vlan for loc in locations)

        if all_same_vlan:
            print(f"  MAC {mac}: All locations have the same VLAN: {first_vlan}.")
            # If VLANs are consistent, we still need to filter out inter-switch links.
            # Any remaining locations are considered valid access ports.
            temp_locations = []
            for switch_name, port_str, vlan_val in locations:
                try:
                    port_int = int(port_str)
                    connection_key = (switch_name, port_int)
                except ValueError:
                    # Port string cannot be converted to int, assume it's an access port
                    # (e.g., "Port-channel1" or other non-numeric port names)
                    print(f"    Port '{port_str}' on switch '{switch_name}' is not a simple integer. Assuming access port.")
                    temp_locations.append((switch_name, port_str, vlan_val))
                    continue
                
                if connection_key in switch_connections:
                    print(f"    Switch-port pair {connection_key} (original port '{port_str}') is an inter-switch link. Ignoring for device location.")
                    # Optionally, you might want to log this or handle it, but it's not a "leak" if VLANs are consistent.
                else:
                    print(f"    Switch-port pair {connection_key} (original port '{port_str}') is an access port.")
                    temp_locations.append((switch_name, port_str, vlan_val))
            processed_locations_for_mac = temp_locations
        else: # VLANs are not the same across locations for this MAC
            print(f"  MAC {mac}: VLANs are NOT the same across locations: {[loc[2] for loc in locations]}")
            # This is a potential VLAN leak scenario.
            # We filter out inter-switch links. Remaining ones are access ports.
            # If a MAC with inconsistent VLANs appears on an inter-switch link, that switch is "leaking".
            temp_locations = []
            for switch_name, port_str, vlan_val in locations:
                print(f"    Checking switch-port pair ({switch_name}, {port_str}) with VLAN {vlan_val}")
                try:
                    port_int = int(port_str) # Convert port from string to int for lookup
                    connection_key = (switch_name, port_int)
                except ValueError:
                    # Port string cannot be converted to int, assume it's an access port
                    print(f"      Port '{port_str}' on switch '{switch_name}' is not a simple integer. Assuming access port.")
                    temp_locations.append((switch_name, port_str, vlan_val))
                    print(f"      Added to potential device locations: ({switch_name}, {port_str}, {vlan_val})")
                    continue

                if connection_key in switch_connections:
                    print(f"      Switch-port pair {connection_key} (original port '{port_str}') is an inter-switch link.")
                    # This MAC on this inter-switch link with a differing VLAN indicates a leak on this switch.
                    leaking_switches.add(switch_name) # Corrected: use add() for sets
                    print(f"      Switch '{switch_name}' added to leaking_switches.")
                else:
                    # Not an inter-switch link, so it's an access port where the device is seen.
                    temp_locations.append((switch_name, port_str, vlan_val))
                    print(f"      Switch-port pair {connection_key} (original port '{port_str}') is NOT in switch_connections. Added to potential device locations.")
            processed_locations_for_mac = temp_locations

    if processed_locations_for_mac:
        # After filtering, if there are multiple locations for the same MAC,
        # you might need further logic to decide the "true" location.
        # For now, we store all determined access port locations.
        # Also, ensure VLAN consistency among these final chosen ports if that's a requirement.
        final_vlans = set(loc[2] for loc in processed_locations_for_mac)
        if len(final_vlans) > 1:
            print(f"  WARNING for MAC {mac}: After filtering, device still appears on access ports with multiple VLANs: {final_vlans}. Locations: {processed_locations_for_mac}")
            # Decide how to handle this: pick one, report error, or list all.
            # For now, adding all to device_locations.
        device_locations[mac].extend(processed_locations_for_mac)
    elif not processed_locations_for_mac and locations: # Original locations existed, but all were filtered out
         print(f"  MAC {mac}: All original locations were filtered out (e.g., all were inter-switch links). No device location determined.")


print("\n==============================")
print("STEP 3 Results:")
print("==============================")
print("Leaking Switches:", leaking_switches)
print("Device Locations (MAC: [(Switch, Port, VLAN), ...]):")
for mac_addr, locs in device_locations.items():
    print(f"  {mac_addr}: {locs}")

'''    for switch_name, port, vlan in locations:
        if (switch_name, port) in switch_connections:
            # Port leading to another switch (trunk port) -> Remove it
            if switch_name not in leaking_switches:  # Only mark switch as leaking if it has more than 1 VLAN
                continue
        new_locations.append((switch_name, port, vlan))'''

    # Store only filtered locations
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
