## Project Overview

This project aims to visualize VLAN trees within computer networks and detect VLAN leakage vulnerabilities. It includes two main components:

1. `scan.sh`: A Bash script that performs SNMP-based scanning of network switches to collect MAC address tables and VLAN data.
2. `VLAN_visualization.py`: A Python script that parses collected data, detects VLAN leaks, and visualizes the network topology.

The solution helps network administrators identify misconfigurations and visualize logical VLAN layouts for better network understanding and security.

## Prerequisites

Before running the project, ensure you have the following installed:

* **Bash Shell** (Linux/macOS)
* **Net-SNMP** (`snmpget`, `snmpwalk`) for network data collection
* **Python 3.8+**
* **Python Packages:**

  * `networkx`
  * `matplotlib`
  * `pyyaml`

Install the required Python packages using:

```bash
pip install networkx matplotlib pyyaml
```

## Installation

Clone the repository and navigate to the project directory:

```bash
git clone <repository_url>
cd <repository_folder>
```

Make the Bash script executable:

```bash
chmod +x scan.sh
```

## Usage

### Step 1: Data Collection

Run the `scan.sh` script to collect MAC address and VLAN data:

```bash
./scan.sh
```

Follow the prompts to enter the IP range and SNMP community string. The data will be saved in the `mac_results` directory.

### Step 2: Configure Topology

Edit the `topology.yaml` file to define switch connections:

```yaml
links:
  - source: Switch1
    source_port: 1
    destination: Switch2
    destination_port: 1
```

### Step 3: Run Analysis and Visualization

Execute the Python script to parse data, detect VLAN leakage, and generate a visualization:

```bash
python3 VLAN_visualization.py
```

The script will generate a visual graph and display it with VLAN segmentation and leakage highlights.

## Configuration Files

* `topology.yaml`: Defines the physical connections between switches.
* `mac_results/`: Contains `.txt` files with MAC address and VLAN data for each switch.

## Output Files

* `mac_results/*.txt`: Raw MAC and VLAN data for each switch.
* `vlan_leaks.txt`: List of detected VLAN leaks.

## Visualization

The graph visualized includes:

* **Switches** (Skyblue nodes, red if VLAN leakage is detected)
* **Devices** (Lightgreen nodes)
* **Inter-switch Links** (Gray edges)
* **Switch-to-Device Links** (Colored by VLAN)

## Testing

* Ensure SNMP is enabled on network switches.
* Use testing environments like GNS3 or EVE-NG for controlled tests.

## Troubleshooting

* If `snmpwalk` fails, verify SNMP community strings and switch configurations.
* For Python errors, ensure required libraries are installed correctly.

## Contributors

* Mikhail Dudzin

---

Vytautas Magnus University - Faculty of Informatics

