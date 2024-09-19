from google.cloud import compute_v1

def get_allocated_ip_ranges(project_id):
    """
    Fetches the list and CIDR of allocated IP ranges for a given VPC under private service access.

    Args:
        project_id: The ID of the Google Cloud project.

    Returns:
        A list of dictionaries, each containing address details.
    """

    client = compute_v1.AddressesClient()

    # List all addresses in the project and region
    request = compute_v1.AggregatedListAddressesRequest(
        project=project_id
    )

    allocated_ranges = []
    # Iterate through all addresses
    for response in client.aggregated_list(request=request):
        # Get the region name (first element of the tuple)
        region_name = response[0]
        # Get the region data (second element of the tuple)
        region_data = response[1]

        for address in region_data.addresses:
            address_data = {
                'address': address.address,
                'address_type': address.address_type,
                'creation_timestamp': address.creation_timestamp,
                'description': address.description,
                'id': address.id,
                'kind': address.kind,
                'label_fingerprint': address.label_fingerprint,
                'name': address.name,
                'network_tier': address.network_tier,
                'purpose': address.purpose,
                'region': address.region.split('/')[-1],  # Extract region name
                'self_link': address.self_link,
                'status': address.status,
                'users': ', '.join(address.users) if address.users else ''
            }
            allocated_ranges.append(address_data)

    return allocated_ranges

# Example usage (you can move this to a Flask app later)
if __name__ == "__main__":
    project_id = "enter_your_project_id_here"
    region = "enter_your_region_here"
    vpc_name = "enter_vpc_name_here"

    allocated_ip_ranges = get_allocated_ip_ranges(project_id, region, vpc_name)

    # For now, just print the data
    for ip_range in allocated_ip_ranges:
        print(ip_range)
