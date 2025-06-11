# Copyright (C) 2021-2025, Hu Xiaonan
# License: MIT License

from abaqus import *
from abaqusConstants import *
import mesh
from dxf2abq import importdxf

MY_CARRIER_MODEL_NAME = 'Model-1'  # Abaqus model containing the carrier part instance.
MY_CARRIER_INSTANCE_NAME = 'STRUCTURE'  # Part instance to which the attachment will be tied.

MY_ATTACHMENT_DXF_NAME = 'attachment'
MY_ATTACHMENT_MATERIAL_EMOD = 79e3
MY_ATTACHMENT_MATERIAL_POISON = 0.42
MY_ATTACHMENT_SHELL_THICKNESS = 10e-6
MY_ATTACHMENT_Z_OFFSET = 5e-3
MY_ATTACHMENT_MESH_SEED_SIZE = 0.01
MY_ATTACHMENT_MESH_SEED_DEVIATION_FACTOR = 0.1  # Set to `None` to disable.
MY_ATTACHMENT_MESH_SEED_MIN_SIZE_FACTOR = 0.1


def M1010_import_attachment_sketch_from_dxf():
    model = mdb.models[MY_CARRIER_MODEL_NAME]
    assembly = model.rootAssembly
    # The abaqus function `importdxf` will import the sketch into the model
    # currently displayed on the viewport, so it is necessary to switch the
    # viewport before importing the sketch to the target model.
    viewport = session.viewports['Viewport: 1']
    viewport.setValues(displayedObject=assembly)
    if model.sketches.has_key(MY_ATTACHMENT_DXF_NAME):
        del model.sketches[MY_ATTACHMENT_DXF_NAME]
    importdxf(fileName=MY_ATTACHMENT_DXF_NAME+'.dxf')


def M1020_create_attachment_part_from_sketch():
    model = mdb.models[MY_CARRIER_MODEL_NAME]
    part = model.Part(name='ATTACHMENT', dimensionality=THREE_D, type=DEFORMABLE_BODY)
    part.BaseShell(sketch=model.sketches[MY_ATTACHMENT_DXF_NAME])

    viewport = session.viewports['Viewport: 1']
    viewport.setValues(displayedObject=part)
    viewport.view.fitView()


def M1030_create_attachment_material_and_section():
    model = mdb.models[MY_CARRIER_MODEL_NAME]
    part = model.parts['ATTACHMENT']
    material = model.Material(name='Material-ATTACHMENT')
    material.Elastic(table=[[MY_ATTACHMENT_MATERIAL_EMOD, MY_ATTACHMENT_MATERIAL_POISON]])
    model.HomogeneousShellSection(
        name='Section-ATTACHMENT',
        material='Material-ATTACHMENT',
        thickness=MY_ATTACHMENT_SHELL_THICKNESS,
    )
    del part.sectionAssignments[:]
    part_face_set = part.Set(faces=part.faces, name='FACES-ALL')
    part.SectionAssignment(region=part_face_set, sectionName='Section-ATTACHMENT')

    viewport = session.viewports['Viewport: 1']
    viewport.setValues(displayedObject=part)
    viewport.partDisplay.setValues(sectionAssignments=ON)
    viewport.view.fitView()


def M1040_create_attachment_instance():
    model = mdb.models[MY_CARRIER_MODEL_NAME]
    part = model.parts['ATTACHMENT']
    assembly = model.rootAssembly
    instance = assembly.Instance(name='ATTACHMENT', part=part, dependent=OFF)
    assembly.translate(
        instanceList=[instance.name],
        vector=[0.0, 0.0, MY_ATTACHMENT_Z_OFFSET],
    )

    viewport = session.viewports['Viewport: 1']
    viewport.setValues(displayedObject=assembly)
    viewport.view.fitView()


def M1050_create_attachment_mesh():
    model = mdb.models[MY_CARRIER_MODEL_NAME]
    assembly = model.rootAssembly
    instance = assembly.instances['ATTACHMENT']

    assembly.seedPartInstance(
        regions=[instance],
        size=MY_ATTACHMENT_MESH_SEED_SIZE,
        deviationFactor=MY_ATTACHMENT_MESH_SEED_DEVIATION_FACTOR,
        minSizeFactor=MY_ATTACHMENT_MESH_SEED_MIN_SIZE_FACTOR,
    )
    elem_type_1 = mesh.ElemType(
        elemCode=S4R,
        elemLibrary=STANDARD,
        secondOrderAccuracy=OFF,
        hourglassControl=DEFAULT,
    )
    elem_type_2 = mesh.ElemType(
        elemCode=S3,
        elemLibrary=STANDARD,
    )
    assembly.setElementType(
        regions=[instance.faces],
        elemTypes=[elem_type_1, elem_type_2],
    )
    assembly.generateMesh(regions=[instance])

    viewport = session.viewports['Viewport: 1']
    viewport.setValues(displayedObject=assembly)
    viewport.assemblyDisplay.setValues(mesh=ON)
    viewport.view.fitView()


def M1060_create_tie_constraint():
    model = mdb.models[MY_CARRIER_MODEL_NAME]
    assembly = model.rootAssembly

    structure_surface = assembly.Surface(
        name='STRUCTURE-TOP',
        side1Faces=assembly.instances['STRUCTURE'].faces,
    )
    attachement_surface = assembly.Surface(
        name='ATTACHMENT-BOTTOM',
        side2Faces=assembly.instances['ATTACHMENT'].faces,
    )
    model.Tie(
        name='TIE-STRUCTURE-ATTACHMENT',
        master=structure_surface, 
        slave=attachement_surface,
        positionToleranceMethod=COMPUTED,
        adjust=OFF, 
        tieRotations=ON,
        thickness=ON,
    )

    viewport = session.viewports['Viewport: 1']
    viewport.setValues(displayedObject=assembly)
    viewport.assemblyDisplay.setValues(step='Step-1')
    viewport.assemblyDisplay.setValues(constraints=ON)
    viewport.view.fitView()


# If the file is used as a script.
if __name__ == '__main__':
    M1010_import_attachment_sketch_from_dxf()
    M1020_create_attachment_part_from_sketch()
    M1030_create_attachment_material_and_section()
    M1040_create_attachment_instance()
    M1050_create_attachment_mesh()
    M1060_create_tie_constraint()

# If the file is named 'abaqusMacro.py' and used as Abaqus macro.
elif __name__ == '_currentMacros':
    print(r"""
 ____________________________________________________________________________ 
|                                                                            |
|     ___           __    ___           ___                     __   __      |
|    / _ )__ ______/ /__ / (_)__  ___ _/ _ | ___ ___ ___ __ _  / /  / /_ __  |
|   / _  / // / __/  '_// / / _ \/ _ `/ __ |(_-<(_-</ -_)  ' \/ _ \/ / // /  |
|  /____/\_,_/\__/_/\_\/_/_/_//_/\_, /_/ |_/___/___/\__/_/_/_/_.__/_/\_, /   |
|                               /___/                               /___/    |
|                                                                            |
|____________________________________________________________________________|
""".lstrip('\n')
    )
