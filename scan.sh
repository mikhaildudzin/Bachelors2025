#!/bin/bash

read -p "Enter starting IP address: " START_IP
read -p "Enter ending IP address: " END_IP
read -p "Enter SNMP community string [default: public]: " COMMUNITY
COMMUNITY=${COMMUNITY:-public}

OUTPUT_DIR="mac_results"
mkdir -p "$OUTPUT_DIR"

START_LAST_OCTET=$(echo "$START_IP" | cut -d. -f4)
END_LAST_OCTET=$(echo "$END_IP" | cut -d. -f4)
IP_PREFIX=$(echo "$START_IP" | cut -d. -f1-3)

declare -A mac_vlan_map

echo "Scanning switches from $START_IP to $END_IP..."

for i in $(seq "$START_LAST_OCTET" "$END_LAST_OCTET"); do
    IP="$IP_PREFIX.$i"
    echo "Querying $IP..."

    HOSTNAME=$(snmpget -v2c -c "$COMMUNITY" -Oqv "$IP" SNMPv2-MIB::sysName.0 2>/dev/null)
    if [[ -z "$HOSTNAME" ]]; then
        echo "  No response from $IP"
        continue
    fi

    echo "  Found $HOSTNAME at $IP"

    FILE="$OUTPUT_DIR/${HOSTNAME}_${IP}.txt"
    echo "Switch: $HOSTNAME ($IP)" > "$FILE"
    echo "MAC Address Table:" >> "$FILE"

    # Walk through FDB (Bridge-MIB, dot1dTpFdbTable)
    snmpwalk -v2c -c "$COMMUNITY" "$IP" 1.3.6.1.2.1.17.4.3.1.1 2>/dev/null | while read -r line; do
        MAC_RAW=$(echo "$line" | awk '{print $NF}')
        MAC=$(printf "%02X:%02X:%02X:%02X:%02X:%02X" $(echo "$MAC_RAW" | tr '.' ' '))
        PORT_INDEX_OID=$(echo "$line" | awk '{print $1}' | sed 's/\.1.3.6.1.2.1.17.4.3.1.1/\.1.3.6.1.2.1.17.4.3.1.2/')
        PORT_INDEX=$(snmpget -v2c -c "$COMMUNITY" -Oqv "$IP" "$PORT_INDEX_OID" 2>/dev/null)
        VLAN_ID=$(snmpwalk -v2c -c "$COMMUNITY" "$IP" 1.3.6.1.2.1.17.7.1.4.5.1.1 2>/dev/null | grep "$PORT_INDEX" | awk -F' = ' '{print $2}' | tr -d '\r')
        
        echo "$MAC (port: $PORT_INDEX) VLAN: $VLAN_ID" >> "$FILE"

        # Save to associative array for leak detection
        KEY="$MAC"
        mac_vlan_map["$KEY"]="${mac_vlan_map[$KEY]} $VLAN_ID@$IP"
    done
done

# Check for MACs appearing in multiple VLANs (possible leak)
echo "VLAN Leak Detection:" > "$OUTPUT_DIR/vlan_leaks.txt"
for MAC in "${!mac_vlan_map[@]}"; do
    UNIQUE_VLANS=$(echo "${mac_vlan_map[$MAC]}" | tr ' ' '\n' | cut -d@ -f1 | sort -u | wc -l)
    if [[ $UNIQUE_VLANS -gt 1 ]]; then
        echo "MAC $MAC appears in multiple VLANs: ${mac_vlan_map[$MAC]}" >> "$OUTPUT_DIR/vlan_leaks.txt"
    fi
done

echo "✅ Scan complete. Results saved in $OUTPUT_DIR/"

