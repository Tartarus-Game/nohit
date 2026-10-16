import xml.etree.ElementTree as ET

tree = ET.parse('repo_badtime/Bad Time Simulator (Sans Fight).caproj')
root = tree.getroot()

print("Root:", root.tag)

# Let's inspect object-folder or families
for family in root.iter('family'):
    name = family.attrib.get('name')
    members = [m.attrib.get('name') for m in family.iter('member')]
    print(f"Family '{name}': {members}")

# Let's inspect objects
print("\nObjects:")
for obj in root.iter('object-type'):
    name = obj.attrib.get('name')
    plugin = obj.attrib.get('plugin-id')
    beh = [b.attrib.get('type') for b in obj.iter('behavior-type')]
    vars = [v.attrib.get('name') for v in obj.iter('instance-variable')]
    if any(k in name.lower() for k in ['heart', 'hitbox', 'bone', 'zone', 'platform', 'blaster', 'attack']):
        print(f"  Object '{name}' ({plugin}): behaviors={beh}, vars={vars}")
