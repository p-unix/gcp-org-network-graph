import sys

from flask import Flask, render_template, request
from google.cloud import resourcemanager_v3
from google.api_core import exceptions
from nw_pycharm_2 import *
from allocated_ip_range import *
import json

app=Flask(__name__,template_folder='template')

@app.route('/', methods=['GET', 'POST'])
def index(input_org_id):
    if request.method == 'POST':
        organization_id = request.form['organization_id']
        try:
            # Fetch organization structure
            nodes, edges = get_organization_structure(organization_id)

            # Generate the graph data in a format suitable for vis.js
            graph_data = {
                'nodes': nodes,
                'edges': edges
            }

            return render_template('index.html', graph_data=graph_data)

        except exceptions.PermissionDenied:
            error_message = f"Permission denied for organization {organization_id}. Please check your permissions."
            return render_template('index.html', error_message=error_message)
        except exceptions.NotFound:
            error_message = f"Organization {organization_id} not found. Please check the organization ID."
            return render_template('index.html', error_message=error_message)
        except Exception as e:
            error_message = f"An error occurred: {str(e)}"
            return render_template('index.html', error_message=error_message)

    return render_template('index.html')

def input_argument_org_id(input_org_id):
    organization_id = input_org_id
    try:
        # Fetch organization structure
        nodes, edges = get_organization_structure(organization_id)
        # Generate the graph data in a format suitable for vis.js
        graph_data = {
            'nodes': nodes,
            'edges': edges
        }
        return render_template('index.html', graph_data=graph_data)

    except exceptions.PermissionDenied:
        error_message = f"Permission denied for organization {organization_id}. Please check your permissions."
        return render_template('index.html', error_message=error_message)
    except exceptions.NotFound:
        error_message = f"Organization {organization_id} not found. Please check the organization ID."
        return render_template('index.html', error_message=error_message)
    except Exception as e:
        error_message = f"An error occurred: {str(e)}"
        return render_template('index.html', error_message=error_message)
    return render_template('index.html')
def get_organization_structure(organization_id):
    parent = f"organizations/{organization_id}"

    print(f"Fetching resources for organization: {organization_id}")

    folder_client = resourcemanager_v3.FoldersClient()
    project_client = resourcemanager_v3.ProjectsClient()

    nodes = [{
        "id": organization_id,
        "label": f"Organization\n{organization_id}",
        "level": 0,
        "color": "#4169E1"  # Royal Blue for organization
    }]
    edges = []

    recursive_list_resources(folder_client, project_client, parent, nodes, edges)

    return nodes, edges

def list_folders(client, parent):
    request = resourcemanager_v3.ListFoldersRequest(parent=parent)
    folders = []
    try:
        page_result = client.list_folders(request=request)
        for response in page_result:
            folders.append({
                "name": response.name,
                "display_name": response.display_name,
                "state": response.state
            })
    except Exception as e:
        print(f"Error listing folders under {parent}: {str(e)}")
    return folders


def list_projects(client, parent):
    request = resourcemanager_v3.ListProjectsRequest(parent=parent)
    projects = []
    try:
        page_result = client.list_projects(request=request)
        for response in page_result:
            if response.state == resourcemanager_v3.Project.State.ACTIVE:
                projects.append({
                    "project_id": response.project_id,
                    "name": response.name,
                    "create_time": response.create_time,
                    "labels": response.labels
                })
    except Exception as e:
        print(f"Error listing projects under {parent}: {str(e)}")
    return projects


def recursive_list_resources(folder_client, project_client, parent, nodes, edges, level=0):
    parent_id = parent.split('/')[-1]

    # List folders
    folders = list_folders(folder_client, parent)
    for folder in folders:
        folder_id = folder['name'].split('/')[-1]
        nodes.append({
            "id": folder_id,
            "label": folder['display_name'],
            "level": level + 1,
            "color": "#FFA500"  # Orange for folders
        })
        edges.append({"from": parent_id, "to": folder_id})
        recursive_list_resources(folder_client, project_client, folder['name'], nodes, edges, level + 1)

    # List projects
    projects = list_projects(project_client, parent)
    for project in projects:
        nodes.append({
            "id": project['project_id'],
            "label": f"{project['project_id']}\n{project['name']}",
            "level": level + 1,
            "color": "#90EE90"  # Light green for projects
        })
        edges.append({"from": parent_id, "to": project['project_id']})

        try:
            vpc_details, vpc_peering_pairs = list_vpc_networks_with_subnets_and_peering(project['project_id'])
            #print details about vpc_details and vpc_peering_pairs
            print(f"vpc_details: {vpc_details}")
            for vpc in vpc_details:

                vpc_node_id = str(project['project_id']) + "_" + str(vpc['name'])
                print(f"vpc_node_id: {vpc_node_id}")

                nodes.append({
                    "id": f"{vpc_node_id}",
                    "label": f"{vpc['name']}",
                    "level": level + 2,
                    "color": "#90d8ee"  # cyan color for vpc
                })
                edges.append({"from": project['project_id'], "to": f"{vpc_node_id}"})

                for subnets in vpc['subnets']:
                    # adding region also to the subnet id so that it remains unique (failed in case of default vpc and default vpcs)
                    subnet_node_id = str(vpc_node_id) + "_" + str(subnets['name']) + "_" + str(subnets['region'])
                    print(f"subnet_node_id: {subnet_node_id}")
                    print(f"subnets: {subnets}")
                    nodes.append({
                        "id": f"{subnet_node_id}",
                        "label": f"{subnets['ip_cidr_range']}\n{subnets['region']}\n{subnets['private_ip_google_access']}\n{subnets['secondary_ip_ranges']}",
                        "level": level + 3,
                        "color": "#ee90b7" # pink color for subnets
                    })
                    edges.append({"from": f"{vpc_node_id}", "to": f"{subnet_node_id}"})

                ###### vpc and subnets complete ######

                #vpc peering has following cases - (a) vpc peering within the same project (b) vpc peering within the same org (c) vpc peering across the orgs (d) vpc peering of PSA (service networking api)
                for vpcpeering in vpc_peering_pairs:
                    print(f"vpcpeering: {vpcpeering}")
                    if (len(vpcpeering) != 0) and (vpcpeering['network'] == vpc['name']):

                        peered_vpc = re.search(r"(?<=networks/)([^/?]+)", vpcpeering['peered_network'])
                        peered_vpc_extracted = peered_vpc.group(1)

                        peered_vpc_project = re.search(r"(?<=projects\/)([^/]+)", vpcpeering['peered_network'])
                        peered_vpc_project_extracted = peered_vpc_project.group(1)

                        # following section is for service networking VPC
                        #case d - service networking api vpc peering
                        if peered_vpc_extracted == 'servicenetworking':
                            gcp_managed_vpc_string = "gcp-managed-vpc-" + str(vpcpeering['network'])
                            nodes.append({
                                "id": f"{peered_vpc_project_extracted}",
                                "label": f"{gcp_managed_vpc_string}",
                                "level": level + 2,
                                "color": "#90d8ee"  # cyan color for vpc
                            })

                            print(f"vpcpeering['network']: {vpcpeering['network']}")
                            vpc_peer_node_id = str(project['project_id']) + "_" + str(vpcpeering['network'])
                            print(f"vpc_peer_node_id: {vpc_peer_node_id}")

                            print(f"gcp_managed_vpc_string: {gcp_managed_vpc_string}")
                            edges.append(
                                {"from": f"{vpc_peer_node_id}", "to": f"{peered_vpc_project_extracted}", "label": "vpc-peering",
                                 "dashes": "true", "color": "#140f0f", "smooth": {"type": "curvedCCW", "roundness": 0.2}})

                        #following section is for case a, b, c
                        else:
                            print(f"vpc peering source network: {vpcpeering['network']}")
                            print(f"peered_vpc_extracted: {peered_vpc_extracted}")

                            print(f"peered_vpc_project_extracted: {peered_vpc_project_extracted}")
                            print(f"project['project_id']: {project['project_id']}")

                            dest_vpc_string = str(f"{peered_vpc_project_extracted}") + "_" + str(f"{peered_vpc_extracted}")
                            source_vpc_string = str(f"{project['project_id']}") + "_" + str(f"{vpcpeering['network']}")

                            project_found_in_nodes_flag = "false"
                            project_found_in_projects_flag = "false"

                            #case b,c - vpc peering within the same org and different orgs
                            if peered_vpc_project_extracted != project['project_id']:
                                print("come here, if they are not equal")
                                #flow has come here, which means that source and destination vpc projects are not equal
                                #check if the project already exists in nodes list
                                for node_index in nodes:
                                    print(f"node_index[id]:  {node_index['id']}")
                                    if node_index['id'] == peered_vpc_project_extracted:
                                        project_found_in_nodes_flag = "true"
                                        print(f"node_index[id]:  {node_index['id']}")
                                        print(f"peered_vpc_project_extracted:  {peered_vpc_project_extracted}")
                                        print(f"project_found_flag:  {project_found_in_nodes_flag}")

                                #check if the peered project is under the same organization
                                for project_index in projects:
                                    if project_index['project_id'] == peered_vpc_project_extracted:
                                        project_found_in_projects_flag = "true"

                                if project_found_in_projects_flag and project_found_in_nodes_flag:
                                    #if above is true, this means that destination project is in the same org and is present in node list, so we will only add edge and not node
                                    edges.append(
                                        {"from": f"{source_vpc_string}", "to": f"{dest_vpc_string}",
                                         "label": "vpc-peering",
                                         "dashes": "true", "color": "#140f0f",
                                         "smooth": {"type": "curvedCCW", "roundness": 0.2}})

                                if (not project_found_in_nodes_flag) and project_found_in_projects_flag:
                                    #if above is true, this means that peered vpc project is not available in nodes list, but is in the same org. Hence, we will only add an edge.
                                    edges.append(
                                        {"from": f"{source_vpc_string}", "to": f"{dest_vpc_string}",
                                         "label": "vpc-peering",
                                         "dashes": "true", "color": "#140f0f",
                                         "smooth": {"type": "curvedCCW", "roundness": 0.2}})

                                if not(project_found_in_nodes_flag) and not(project_found_in_projects_flag):
                                    #if above is true, this means that peered vpc project is not available in nodes list and also not in org. Hence, we will have to add a node also, along with edge.
                                    #adding a node for the gcp project not in the org
                                    nodes.append({
                                        "id": f"{peered_vpc_project_extracted}",
                                        "label": f"{peered_vpc_project_extracted}",
                                        "level": level + 1,
                                        "color": "#90EE90"  # Light green for projects
                                    })
                                    #adding a node for the vpc under above gcp project
                                    nodes.append({
                                        "id": f"{dest_vpc_string}",
                                        "label": f"{peered_vpc_extracted}",
                                        "level": level + 2,
                                        "color": "#90d8ee"  # cyan color for vpc
                                    })
                                    #connecting gcp project and vpc
                                    edges.append({"from": f"{peered_vpc_project_extracted}", "to": f"{dest_vpc_string}"})
                                    #connecting both the vpcs
                                    edges.append(
                                        {"from": f"{dest_vpc_string}", "to": f"{source_vpc_string}",
                                         "label": "vpc-peering",
                                         "dashes": "true", "color": "#140f0f",
                                         "smooth": {"type": "curvedCCW", "roundness": 0.2}})

                            else:
                                #this is the case where source and destination vpcs are in the project
                                edges.append({"from": vpcpeering['network'], "to": f"{peered_vpc_extracted}", "label": "vpc-peering",
                                 "dashes": "true", "color": "#140f0f", "smooth": {"type": "curvedCCW", "roundness": 0.2}})
        except:
            print(f"project: {project['project_id']} does not Compute Engine API Enabled")
        else:
            print("some error occurred")

        #cloud nat code here
        try:
            nat_configs_by_router = list_nat_configs(project['project_id'])
            if nat_configs_by_router:
                print("NAT configurations found:")
                for router_name, nat_configs in nat_configs_by_router.items():
                    print(f"Router: {router_name}")
                    for nat_config in nat_configs:
                        print(f"nat_config: {nat_config}")
                        nodes.append({
                            "id": f"{router_name}",
                            "label": f"{nat_config['name']}\n{nat_config['region']}\n{nat_config['vpc_network']}",
                            "level": level + 4,
                            "color": "#e3d914"  # yellow color for cloud nat
                        })
                        nat_vpc_string = str(project['project_id']) + "_" + str(nat_config['vpc_network'])
                        print(f"nat_vpc_string: {nat_vpc_string}")
                        edges.append({
                            "to": f"{router_name}",
                            "from": f"{nat_vpc_string}"
                        })
        except:
            print(f"project: {project['project_id']} does not Compute Engine API Enabled")
        else:
            print("some error occurred")
            ######
    #shared vpc host-service vpc start
    for project in projects:
        try:
            host_project_id = sample_get_xpn_host(project['project_id'])
            print(f"host_project_id: {host_project_id} is the host project of service project : {project['project_id']}")
            edges.append({"from": f"{host_project_id}", "to": project['project_id'], "label": "shared-vpc-projects",
                          "dashes": "true", "color": "#140f0f", "smooth": {"type": "curvedCCW", "roundness": 0.2}})
        except:
            print(f"project: {project['project_id']} does not have a service project")
        else:
            print("some error occurred")
        #shared vpc host-service vpc end
        ######


######
#cloud nat code here start
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

            vpcnetwork = router.network
            match = re.search(r"/networks/([^/]+)$", vpcnetwork)
            vpc_cloud_nat = match.group(1)

            for nat_config in router.nats:
                # Extract subnetwork and VPC network from source_subnetwork_ip_ranges_to_nat
                subnetwork = None
                vpc_network = None
                if nat_config.source_subnetwork_ip_ranges_to_nat:
                    subnetwork_range = nat_config.source_subnetwork_ip_ranges_to_nat[0]

                    # Correctly extract VPC network and subnetwork
                    parts = subnetwork_range.split('/')

                    vpc_network = vpc_cloud_nat

                # Get NAT IP addresses from nat_ip_allocate_option
                nat_ip_addresses = nat_config.nat_ip_allocate_option.split(
                    ',') if nat_config.nat_ip_allocate_option else []

                nat_config_details = {
                    'name': nat_config.name,
                    'region': region,  # Add the region
                    'vpc_network': vpc_network,  # Add the VPC network
                }
                nat_configs.append(nat_config_details)
            nat_configs_by_router[router.name] = nat_configs

    return nat_configs_by_router
#cloud nat code here end
######

######
def sample_get_xpn_host(svc_project_id):  # Create a client
    client = compute_v1.ProjectsClient()
    # Initialize request argument(s)
    request1 = compute_v1.GetXpnHostProjectRequest(project=svc_project_id)
    
    
    # Make the request
    response1 = client.get_xpn_host(request=request1)
    #response2 = client.get_xpn_resources(request=request2)
    # Handle the response
    print(f"response1 - host project is : {response1}")
    return str(response1.name)
    #print(f"response2: {response2}")

######

def generate_html(organization_id, nodes, edges):
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>GCP Organization Structure</title>
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
        <h1>GCP Organization Structure: {organization_id}</h1>
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
                        face: 'arial'
                    }},
                    margin: 10,
                    widthConstraint: {{ minimum: 100, maximum: 250 }}
                }},
                edges: {{
                    arrows: 'to',
                    smooth: 
                    {{
                        type: "cubicBezier",
                        forceDirection: "vertical"
                    }},
                }},
                layout: {{
                    hierarchical: {{
                        direction: 'UD',
                        sortMethod: 'directed',
                        levelSeparation: 150,
                        nodeSpacing: 200
                    }}
                }},
                physics: false
            }};
            var network = new vis.Network(container, data, options);
        </script>
    </body>
    </html>
    """
    with open(f"gcp_organization_{organization_id}_structure.html", "w") as f:
        f.write(html_content)

def main():
    # Check if any arguments were provided
    if len(sys.argv) > 1:
        print("Arguments provided:")
        for i, arg in enumerate(sys.argv[1:], start=1):
            print(f"Argument {i}: {arg}")
        input_org_id = sys.argv[1]
        input_argument_org_id(input_org_id)

    else:
        print("No arguments provided.")
        app.run(debug=True)

if __name__ == '__main__':
    main()
