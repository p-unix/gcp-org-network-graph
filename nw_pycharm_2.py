from google.cloud import compute_v1
from google.auth import default
import os
import json
import re

import google.auth
from googleapiclient import discovery
from google.auth.transport.requests import Request


def list_nat_configs(project_id):
    """Lists all NAT configurations associated with Cloud Routers in all regions of a project,
    including detailed information about each NAT configuration.

    Args:
        project_id: The Google Cloud project ID.

    Returns:
        A dictionary where keys are router names and values are lists of dictionaries,
        each containing detailed information about a NAT configuration.
    """

    router_client = compute_v1.RoutersClient()
    nat_configs_by_router = {}

    # List all regions in the project
    regions_client = compute_v1.RegionsClient()
    regions = [region.name for region in regions_client.list(project=project_id)]

    for region in regions:
        request = compute_v1.ListRoutersRequest(
            project=project_id,
            region=region,
        )

        for router in router_client.list(request=request):
            nat_configs = []
            for nat_config in router.nats:
                # Extract subnetwork from source_subnetwork_ip_ranges_to_nat
                subnetwork = None
                if nat_config.source_subnetwork_ip_ranges_to_nat:
                    subnetwork_range = nat_config.source_subnetwork_ip_ranges_to_nat[0]
                    subnetwork = subnetwork_range.split('/')[-1]  # Get the last part after the slash

                # Get NAT IP addresses from nat_ip_allocate_option
                nat_ip_addresses = nat_config.nat_ip_allocate_option.split(
                    ',') if nat_config.nat_ip_allocate_option else []

                nat_config_details = {
                    'name': nat_config.name
                }
                nat_configs.append(nat_config_details)
            nat_configs_by_router[router.name] = nat_configs

    return nat_configs_by_router


def list_vpc_networks_with_subnets_and_peering(project_id):
    credentials, _ = default()
    network_client = compute_v1.NetworksClient(credentials=credentials)
    subnet_client = compute_v1.SubnetworksClient(credentials=credentials)
    region_client = compute_v1.RegionsClient(credentials=credentials)

    vpc_details = []
    vpc_peering_pairs = []

    # List all regions
    region_request = compute_v1.ListRegionsRequest(project=project_id)
    regions = [region.name for region in region_client.list(request=region_request)]

    # List all VPC networks
    network_request = compute_v1.ListNetworksRequest(project=project_id)
    networks = network_client.list(request=network_request)

    for network in networks:
        vpc_name = network.name
        subnets = []

        # List subnets for each region
        for region in regions:
            subnet_request = compute_v1.ListSubnetworksRequest(project=project_id, region=region)
            for subnet in subnet_client.list(request=subnet_request):
                if subnet.network.split('/')[-1] == vpc_name:
                    subnets.append({
                        'name': subnet.name,
                        'region': region,
                        'ip_cidr_range': subnet.ip_cidr_range,
                        'private_ip_google_access': subnet.private_ip_google_access,
                        'secondary_ip_ranges': [
                            {'range_name': range.range_name, 'ip_cidr_range': range.ip_cidr_range}
                            for range in subnet.secondary_ip_ranges

                        ]
                    })

        vpc_details.append({
            'name': vpc_name,
            'subnets': subnets
        })

        vpc_peering_pairs = list_vpc_peerings(project_id)

        '''
        # Collect VPC peering information
        for peering in network.peerings:
            if peering.state == compute_v1.NetworkPeering.State.ACTIVE:
                peer_network = peering.network.split('/')[-1]
                vpc_peering_pairs.append((vpc_name, peer_network))
                print("this is the vpc peering stage")
        '''

    return vpc_details, vpc_peering_pairs


########### START : this is a custom function from gemini-vpc-peering.py file #########

def list_vpc_peerings(project_id):
    client = compute_v1.NetworksClient()

    # List all networks in the project
    networks = client.list(project=project_id)

    peerings = []

    # Iterate through networks and check for peerings
    for network in networks:
        for peering in network.peerings:
            peerings.append({
                'network': network.name,
                'peered_network': peering.network,
                'state': peering.state,
                'auto_create_routes': peering.auto_create_routes
            })

    return peerings


########### END : this is a custom function from gemini-vpc-peering.py file #########

def generate_network_visualization(project_id, vpc_details, vpc_peering_pairs):
    nodes = []
    edges = []

    # Add project node
    nodes.append({
        "id": project_id,
        "label": f"gcp project : {project_id}",
        "level": 0
    })

    for vpc in vpc_details:
        vpc_name = vpc['name']
        subnets = vpc['subnets']

        # Add VPC node
        nodes.append({
            "id": vpc_name,
            "label": f"vpc : {vpc_name}",
            "level": 1
        })
        edges.append({"from": project_id, "to": vpc_name})

        for subnet in subnets:
            subnet_name = subnet['name']
            # Create a detailed label for the subnet
            subnet_label = (
                f"subnet : {subnet_name}\n"
                f"CIDR : {subnet['ip_cidr_range']}\n"
                f"Region : {subnet['region']}\n"
                f"PGA : {'On' if subnet['private_ip_google_access'] else 'Off'}\n"
            )

            # Add secondary ranges if any
            if subnet['secondary_ip_ranges']:
                subnet_label += "Secondary ranges:\n"
                for range in subnet['secondary_ip_ranges']:
                    subnet_label += f"  {range['range_name']}: {range['ip_cidr_range']}\n"

            # Add subnet node
            nodes.append({
                "id": subnet_name,
                "label": subnet_label.strip(),
                "level": 2
            })
            edges.append({"from": vpc_name, "to": subnet_name})

    for peering in vpc_peering_pairs:
        print(f"Network: {peering['network']}")
        print(f"Peered Network: {peering['peered_network']}")
        match = re.search(r"(?<=networks/)([^/?]+)", peering['peered_network'])
        extracted_text = match.group(1)
        print(f"extracted_text: {extracted_text}")

        if extracted_text == 'servicenetworking':
            # add a vpc node

            gcp_managed_vpc_string = "gcp-managed-vpc-" + str(peering['network'])
            print(gcp_managed_vpc_string)

            edges.append({"from": peering['network'], "to": gcp_managed_vpc_string, "smooth": {type: "curvedCW", "roundness": 0.2} ,"dashes": 'true', "color": 'red'})
            allocated_ip_range_string2 = list_allocated_ranges(project_id, peering['network'])
            print(f"allocated_ip_range_string2: {allocated_ip_range_string2}")
            nl = '\n'

            # List all routes
            compute = discovery.build('compute', 'v1')
            routes_request = compute.routes().list(project=project_id, filter=f"network eq .*/{peering['network']}$")
            destination_ip_range = "destination_ip_range :" + "\n"
            if routes_request:
                print(routes_request)
            else:
                print("Nothing in Route Request")

            while routes_request is not None:
                routes_response = routes_request.execute()

                for route in routes_response.get('items', []):
                    # print(route['destRange'] + "and" + route['nextHopPeering'])
                    # Check if the route is an imported one from this peering
                    if 'nextHopPeering' in route and route['nextHopPeering'] == peering['peered_network']:
                        print(f"  Destination: {route['destRange']}")
                        destination_ip_range = destination_ip_range + route['destRange'] + "\n"
                        print(destination_ip_range)

                routes_request = compute.routes().list_next(previous_request=routes_request,
                                                            previous_response=routes_response)

            nodes.append({
                "id": f"{gcp_managed_vpc_string}",
                "label": f"vpc : {extracted_text} {nl}{allocated_ip_range_string2}",
                "level": 1
            })

        print(f"State: {peering['state']}")
        print(f"Auto Create Routes: {peering['auto_create_routes']}")
        print("-" * 40)

        if extracted_text != 'servicenetworking':
            edges.append({"from": peering['network'], "to": extracted_text, "smooth": {type: "curvedCW", "roundness": 0.2},"dashes": 'true', "color": 'green'})
            print(f"normal vpc peering - from {peering['network']} to {extracted_text}")

    return nodes, edges


######## Start Allocted IP range ####

def list_allocated_ranges(project_id, network):
    """Lists allocated IP ranges for services in a GCP project and network."""

    credentials, _ = default()
    service_networking = discovery.build('servicenetworking', 'v1', credentials=credentials)
    compute = discovery.build('compute', 'v1', credentials=credentials)

    # Construct the parent resource name
    parent = 'services/servicenetworking.googleapis.com'

    # Construct the network resource name
    network_name = f'projects/{project_id}/global/networks/{network}'

    try:
        # List the connections
        request = service_networking.services().connections().list(parent=parent, network=network_name)
        response = request.execute()

        if 'connections' in response:
            for connection in response['connections']:
                print(f"Service: {connection.get('service', 'N/A')}")
                print(f"Network: {connection.get('network', 'N/A')}")
                print("Allocated IP Ranges:")
                for range_name in connection.get('reservedPeeringRanges', []):
                    # Fetch the actual CIDR range
                    range_request = compute.globalAddresses().get(project=project_id, address=range_name)
                    range_response = range_request.execute()
                    cidr = range_response.get('address', 'N/A')
                    prefix_length = range_response.get('prefixLength', 'N/A')
                    print(f"  - {range_name}: {cidr}/{prefix_length}")
                    allocated_ip_range_string = f" {range_name} : {cidr}/{prefix_length}"

                    return allocated_ip_range_string

                print("---")
        else:
            print("No connections found.")

    except Exception as e:
        print(f"An error occurred: {e}")


######## End AllocatedA IP Range ###

def create_html(project_id, nodes, edges):
    html_content = f"""
    <html>
    <head>
        <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
        <style type="text/css">
            #mynetwork {{
                width: 100%;
                height: 800px;
                border: 1px solid lightgray;
            }}
        </style>
    </head>
    <body>
    <div id="mynetwork"></div>
    <script type="text/javascript">
        var nodes = new vis.DataSet({json.dumps(nodes)});
        var edges = new vis.DataSet({json.dumps(edges)});
        var container = document.getElementById('mynetwork');
        var data = {{
            nodes: nodes,
            edges: edges
        }};
        var options = {{
            nodes: {{
                shape: 'box',
                font: {{
                    size: 12,
                    face: 'arial',
                    multi: 'html',
                    align: 'middle'
                }},
                margin: 10,
                widthConstraint: {{ minimum: 150, maximum: 300 }},
                physics: false
            }},
            edges: {{
                smooth: {{
                    type: "cubicBezier",
                    forceDirection: "vertical"
                }},
                font: {{
                    size: 12,
                    face: 'arial',
                    align: 'middle'
                }},
                arrows: {{
                    to: {{enabled: false}},
                    from: {{enabled: false}}
                }}
            }},
            layout: {{
                hierarchical: {{
                    direction: "UD",
                    sortMethod: "directed",
                    nodeSpacing: 200,
                    levelSeparation: 250
                }}
            }},
            physics: {{
                hierarchicalRepulsion: {{
                    centralGravity: 0
                }},
                minVelocity: 0.75,
                solver: "hierarchicalRepulsion"
            }}
        }};
        var network = new vis.Network(container, data, options);
    </script>
    </body>
    </html>
    """

    with open(f"{project_id}_vpc_networks.html", "w") as f:
        f.write(html_content)


def main():
    # Get the project ID from environment variable
    project_id = os.environ.get('PROJECT_ID')

    if not project_id:
        raise ValueError("Please set the GOOGLE_CLOUD_PROJECT environment variable")

    print(f"Fetching VPC information for project: {project_id}")
    vpc_details, vpc_peering_pairs = list_vpc_networks_with_subnets_and_peering(project_id)

    print("Generating network visualization...")
    nodes, edges = generate_network_visualization(project_id, vpc_details, vpc_peering_pairs)

    print("Creating HTML file...")
    create_html(project_id, nodes, edges)

    print(f"Done! Visualization saved as {project_id}_vpc_networks.html")


if __name__ == "__main__":
    main()
