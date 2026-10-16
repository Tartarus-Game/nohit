import xml.etree.ElementTree as ET

tree = ET.parse('repo_badtime/Event sheets/Battle.xml')
root = tree.getroot()

def elem_to_str(elem, depth=0):
    indent = "  " * depth
    res = []
    if elem.tag == 'variable':
        res.append(f"{indent}VAR {elem.attrib.get('name')} = {elem.attrib.get('initial-value')} ({elem.attrib.get('type')})")
    elif elem.tag == 'event-group':
        res.append(f"{indent}GROUP '{elem.attrib.get('title')}'")
    elif elem.tag == 'event-block':
        res.append(f"{indent}EVENT BLOCK:")
    elif elem.tag == 'condition':
        c_id = elem.attrib.get('id')
        name = elem.attrib.get('name')
        params = [p.text for p in elem.findall('param')]
        inverted = " [INVERTED]" if elem.attrib.get('inverted') == "1" else ""
        res.append(f"{indent}  COND: {name} (id={c_id}){inverted} params={params}")
    elif elem.tag == 'action':
        a_id = elem.attrib.get('id')
        name = elem.attrib.get('name')
        params = [p.text for p in elem.findall('param')]
        res.append(f"{indent}  ACT: {name} (id={a_id}) params={params}")

    for child in elem:
        if child.tag not in ['param', 'behavior']:
            sub = elem_to_str(child, depth + 1)
            if sub:
                res.append(sub)
    return "\n".join(res)

for elem in root.iter('event-group'):
    if elem.attrib.get('title') == 'PlayerDamage':
        print(elem_to_str(elem))
        break
