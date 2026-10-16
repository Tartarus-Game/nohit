import xml.etree.ElementTree as ET

tree = ET.parse('repo_badtime/Event sheets/Battle.xml')
root = tree.getroot()

print("Root tag:", root.tag)
# Let's list event groups in Battle.xml
groups = []
for elem in root.iter('event-group'):
    title = elem.attrib.get('title')
    desc = elem.attrib.get('description', '')
    groups.append((title, desc))

print(f"Total event groups: {len(groups)}")
for title, desc in groups:
    print(f"  Group: '{title}' - {desc}")
