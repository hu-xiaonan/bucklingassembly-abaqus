from abaqus import *
from abaqusConstants import *
import interaction
import mesh
import regionToolset
import step

MEMBRANE_LEN_X = 10.0
MEMBRANE_LEN_Y = 10.0
INTERCEPT = 2.0
MEMBRANE_THICKNESS = 0.3
PROTRUSION_RADIUS = 0.2
PROTRUSION_FEED = 5
MEMBRANE_MESH_SIZE = 0.2
PROTRUSION_MESH_SIZE = 0.1
MEMBRANE_CORNER_SHRINKAGE = 0.2

model = mdb.models['Model-1']
assembly = model.rootAssembly

membrane_sketch = model.ConstrainedSketch(name='__profile__', sheetSize=200.0)
membrane_sketch.rectangle(
    point1=(-MEMBRANE_LEN_X/2.0, -MEMBRANE_LEN_Y/2.0),
    point2=(+MEMBRANE_LEN_X/2.0, +MEMBRANE_LEN_Y/2.0),
)
membrane_part = mdb.models['Model-1'].Part(name='MEMBRANE', dimensionality=THREE_D, type=DEFORMABLE_BODY)
membrane_part.BaseShell(sketch=membrane_sketch)
del model.sketches['__profile__']
del membrane_sketch

if model.sketches.has_key('MEMBRANE_PARTITION'):
    del model.sketches['MEMBRANE_PARTITION']
membrane_partition_sketch = model.ConstrainedSketch(name='MEMBRANE_PARTITION', sheetSize=200.0)
membrane_partition_sketch.Line(
    point1=(+MEMBRANE_LEN_X/2.0, +MEMBRANE_LEN_Y/2.0-INTERCEPT),
    point2=(+MEMBRANE_LEN_X/2.0-INTERCEPT, +MEMBRANE_LEN_Y/2.0),
)
membrane_partition_sketch.Line(
    point1=(-MEMBRANE_LEN_X/2.0, +MEMBRANE_LEN_Y/2.0-INTERCEPT),
    point2=(-MEMBRANE_LEN_X/2.0+INTERCEPT, +MEMBRANE_LEN_Y/2.0),
)
membrane_partition_sketch.Line(
    point1=(-MEMBRANE_LEN_X/2.0, -MEMBRANE_LEN_Y/2.0+INTERCEPT),
    point2=(-MEMBRANE_LEN_X/2.0+INTERCEPT, -MEMBRANE_LEN_Y/2.0),
)
membrane_partition_sketch.Line(
    point1=(+MEMBRANE_LEN_X/2.0, -MEMBRANE_LEN_Y/2.0+INTERCEPT),
    point2=(+MEMBRANE_LEN_X/2.0-INTERCEPT, -MEMBRANE_LEN_Y/2.0),
)

membrane_part.PartitionFaceBySketch(
    faces=membrane_part.faces,
    sketch=membrane_partition_sketch,
)


def get_neohooke_coeff(E, nu):
    C10 = E/(4.0*(1.0+nu))
    D = 6.0*(1.0-2.0*nu)/E
    return (C10, D)


elastomer = model.Material(name='ELASTOMER')
elastomer.Hyperelastic(
    materialType=ISOTROPIC,
    testData=OFF,
    type=NEO_HOOKE, 
    volumetricResponse=VOLUMETRIC_DATA,
    table=[get_neohooke_coeff(1.0, 0.49)],
)
model.HomogeneousShellSection(
    name='HOMOSHELL-ELASTOMER',
    material='ELASTOMER',
    thickness=MEMBRANE_THICKNESS,
)

rigid_material = model.Material(name='RIGID')
rigid_material.Elastic(table=[[100000.0, 0.0]])
model.HomogeneousShellSection(
    name='HOMOSHELL-RIGID',
    material='RIGID',
    thickness=MEMBRANE_THICKNESS,
)

membrane_part.Set(
    name='CELLS-ELASTIC',
    faces=membrane_part.faces.getSequenceFromMask(mask=('[#10 ]', ), ),
)
membrane_part.Set(
    name='CELLS-RIGID',
    faces=membrane_part.faces.getSequenceFromMask(mask=('[#f ]', ), ),
)
del membrane_part.sectionAssignments[:]
membrane_part.SectionAssignment(
    region=membrane_part.sets['CELLS-ELASTIC'],
    sectionName='HOMOSHELL-ELASTOMER',
)
membrane_part.SectionAssignment(
    region=membrane_part.sets['CELLS-RIGID'],
    sectionName='HOMOSHELL-RIGID',
)

membrane_instance = assembly.Instance(name='MEMBRANE', part=membrane_part, dependent=OFF)
EPS = 1e-5
membrane_vertices = membrane_instance.vertices
assembly.Set(
    name='VERTICES-MEMBRANE-XPOS-YPOS',
    vertices=membrane_vertices.getByBoundingBox(xMin=+MEMBRANE_LEN_X/2.0-EPS, yMin=+MEMBRANE_LEN_Y/2.0-EPS),
)
assembly.Set(
    name='VERTICES-MEMBRANE-XNEG-YPOS',
    vertices=membrane_vertices.getByBoundingBox(xMax=-MEMBRANE_LEN_X/2.0+EPS, yMin=+MEMBRANE_LEN_Y/2.0-EPS),
)
assembly.Set(
    name='VERTICES-MEMBRANE-XNEG-YNEG',
    vertices=membrane_vertices.getByBoundingBox(xMax=-MEMBRANE_LEN_X/2.0+EPS, yMax=-MEMBRANE_LEN_Y/2.0+EPS),
)
assembly.Set(
    name='VERTICES-MEMBRANE-XPOS-YNEG',
    vertices=membrane_vertices.getByBoundingBox(xMin=+MEMBRANE_LEN_X/2.0-EPS, yMax=-MEMBRANE_LEN_Y/2.0+EPS),
)
assembly.seedPartInstance(
    regions=[membrane_instance],
    size=MEMBRANE_MESH_SIZE,
    deviationFactor=0.1,
    minSizeFactor=0.1,
)
assembly.generateMesh(regions=[membrane_instance])

protrusion_sketch = model.ConstrainedSketch(name='__profile__', sheetSize=200.0)
protrusion_sketch.CircleByCenterPerimeter(center=(0.0, 0.0), point1=(PROTRUSION_RADIUS, 0.0))
protrusion_part = model.Part(name='PROTRUSION', dimensionality=THREE_D, type=DISCRETE_RIGID_SURFACE)
protrusion_part.BaseShell(sketch=protrusion_sketch)
del mdb.models['Model-1'].sketches['__profile__']
del protrusion_sketch
protrusion_part.ReferencePoint(
    point=protrusion_part.InterestingPoint(edge=protrusion_part.edges[0], rule=CENTER)
)
protrusion_instance = assembly.Instance(name='PROTRUSION', part=protrusion_part, dependent=OFF)
assembly.seedPartInstance(
    regions=[protrusion_instance],
    size=PROTRUSION_MESH_SIZE,
    deviationFactor=0.1,
    minSizeFactor=0.1,
)
assembly.generateMesh(regions=[protrusion_instance])
assembly.Set(referencePoints=[protrusion_instance.referencePoints[2]], name='RP-PROTRUSION')

assembly.translate(instanceList=['PROTRUSION'], vector=(0.0, 0.0, -MEMBRANE_THICKNESS/2.0))
model.ContactProperty('IntProp-1')
model.interactionProperties['IntProp-1'].TangentialBehavior(formulation=FRICTIONLESS)
model.interactionProperties['IntProp-1'].NormalBehavior(pressureOverclosure=HARD)
model.ContactStd(name='Int-1', createStepName='Initial')
model.interactions['Int-1'].includedPairs.setValuesInStep(stepName='Initial', useAllstar=ON)
model.interactions['Int-1'].contactPropertyAssignments.appendInStep(
    stepName='Initial',
    assignments=((GLOBAL, SELF, 'IntProp-1'), ),
)

model.StaticStep(
    name='Step-1',
    previous='Initial',
    maxNumInc=1000,
    initialInc=1.0,
    minInc=1e-10,
    nlgeom=ON,
)
model.fieldOutputRequests['F-Output-1'].setValues(
    variables=['U', 'LE', 'S', 'CSTATUS'],
    numIntervals=20,
)

model.DisplacementBC(
    name='MEMBRANE-XPOS-YPOS',
    createStepName='Step-1',
    region=assembly.sets['VERTICES-MEMBRANE-XPOS-YPOS'],
    u1=-MEMBRANE_LEN_X/2.0*MEMBRANE_CORNER_SHRINKAGE,
    u2=-MEMBRANE_LEN_Y/2.0*MEMBRANE_CORNER_SHRINKAGE,
    u3=0,
    ur1=UNSET, ur2=UNSET, ur3=UNSET, 
)
model.DisplacementBC(
    name='MEMBRANE-XNEG-YPOS',
    createStepName='Step-1',
    region=assembly.sets['VERTICES-MEMBRANE-XNEG-YPOS'],
    u1=+MEMBRANE_LEN_X/2.0*MEMBRANE_CORNER_SHRINKAGE,
    u2=-MEMBRANE_LEN_Y/2.0*MEMBRANE_CORNER_SHRINKAGE,
    u3=0,
    ur1=UNSET, ur2=UNSET, ur3=UNSET, 
)
model.DisplacementBC(
    name='MEMBRANE-XNEG-YNEG',
    createStepName='Step-1',
    region=assembly.sets['VERTICES-MEMBRANE-XNEG-YNEG'],
    u1=+MEMBRANE_LEN_X/2.0*MEMBRANE_CORNER_SHRINKAGE,
    u2=+MEMBRANE_LEN_Y/2.0*MEMBRANE_CORNER_SHRINKAGE,
    u3=0,
    ur1=UNSET, ur2=UNSET, ur3=UNSET, 
)
model.DisplacementBC(
    name='MEMBRANE-XPOS-YNEG',
    createStepName='Step-1',
    region=assembly.sets['VERTICES-MEMBRANE-XPOS-YNEG'],
    u1=-MEMBRANE_LEN_X/2.0*MEMBRANE_CORNER_SHRINKAGE,
    u2=+MEMBRANE_LEN_Y/2.0*MEMBRANE_CORNER_SHRINKAGE,
    u3=0,
    ur1=UNSET, ur2=UNSET, ur3=UNSET, 
)
model.DisplacementBC(
    name='PROTRUSION',
    createStepName='Step-1',
    region=assembly.sets['RP-PROTRUSION'],
    u1=0, u2=0, u3=PROTRUSION_FEED, ur1=0, ur2=0, ur3=0,
)

job = mdb.Job(name='Job-1', model='Model-1')
job.writeInput(consistencyChecking=OFF)

mdb.saveAs(pathName='model')
