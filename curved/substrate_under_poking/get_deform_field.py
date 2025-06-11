from abaqus import *
from abaqusConstants import *
import visualization

import numpy as np

session.openOdb('Job-1.odb')
odb = session.odbs['Job-1.odb']
assembly = odb.rootAssembly
instance = assembly.instances['MEMBRANE']

node_label_to_index_map = dict((node.label, i) for i, node in enumerate(instance.nodes))
COORD0_all_nodes = np.zeros((len(node_label_to_index_map), 3))
for node in instance.nodes:
    COORD0_all_nodes[node_label_to_index_map[node.label], :] = node.coordinates

output_data = []
frame = odb.steps['Step-1'].frames[-1]
for v in frame.fieldOutputs['U'].values:
    if v.instance.name != instance.name:
        continue
    coord0 = COORD0_all_nodes[node_label_to_index_map[v.nodeLabel], :]
    coord1 = coord0 + v.data
    output_data.append((coord0[0], coord0[1], coord1[0], coord1[1], coord1[2]))
assert len(output_data) == len(COORD0_all_nodes)
with open('curved_surf_deform_field.txt', 'w') as f:
    f.write('# u v x y z\n')
    np.savetxt(f, output_data)
