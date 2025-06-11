# Copyright (C) 2021-2025, Hu Xiaonan
# License: MIT License

import os
from pathlib import Path
import numpy as np
from scipy.interpolate import CloughTocher2DInterpolator
from scipy.differentiate import jacobian  # Requires SciPy 1.15.0 or later.

os.chdir(Path(__file__).parent.resolve())


def my_map(points_2d):
    # CHANGE THIS FUNCTION ON YOUR NEED.

    """
    Map multiple 2D points from the flat precursor to their final locations
    on the curved surface.

    Parameters
    ----------
    points_2d : numpy.ndarray, shape=(N, 2)
        Points on the planar precursor.

    Returns
    -------
    numpy.ndarray, shape=(N, 6)
        Mapped coordinates and rotation vectors for each point, where each row
        contains (x, y, z, urx, ury, urz) for the point.

    """
    # Calculate the point location after buckling assembly. The following two
    # parameters should be consistent with that in the `main-classical.py`
    # script.
    MY_SHRINKING_CENTER = np.asarray([0, 0])
    MY_SHRINKAGE = 0.3
    points_2d = np.asarray(points_2d)
    points_2d_shrunk = points_2d-MY_SHRINKAGE*(points_2d-MY_SHRINKING_CENTER)

    # The demonstrative data file `curved_surf_deform_field.txt` contain five
    # columns: u, v, x, y, z
    # 
    # (u, v): 2D coordinates on the undeformed configuration
    # (x, y, z): Corresponding 3D coordinates on the deformed configuration
    deform_field = np.loadtxt('curved_surf_deform_field.txt')
    undeformed_2d = deform_field[:, 0:2]
    deformed_3d = deform_field[:, 2:5]
    return map_from_discrete_deform_field(points_2d_shrunk, undeformed_2d, deformed_3d)


def map_from_discrete_deform_field(points_2d, undeformed_2d, deformed_3d):
    points_2d = np.asarray(points_2d)
    field = CloughTocher2DInterpolator(undeformed_2d, deformed_3d)
    points_3d = field(points_2d)
    J = jacobian(lambda x: field(x.T).T, points_2d.T)
    Ju = J.df[:, 0, :].T
    Jv = J.df[:, 1, :].T
    n1 = Ju/np.linalg.norm(Ju, axis=1)[:, np.newaxis]
    n2 = Jv/np.linalg.norm(Jv, axis=1)[:, np.newaxis]
    n3 = np.cross(n1, n2)
    Q = np.transpose([n1, n2, n3], axes=(1, 2, 0))
    rotvec = rotmat_to_rotvec(Q)
    return points_3d, rotvec


def rotmat_to_rotvec(Q):
    """
    Convert 3x3 rotation matrix to rotation vector (axis-angle form).

    Parameters
    ----------
    Q : numpy.ndarray
        Rotation matrix or matrices, can be either 2D (shape=(3, 3)) or 3D
        (shape=(N, 3, 3)), where N is the number of rotation matrices.

    Returns
    -------
    numpy.ndarray
        Rotation vector or vectors, shape=(3,) if Q is 2D, or shape=(N, 3) if Q
        is 3D. The vector direction is the rotation axis, magnitude is the
        rotation angle in radians.

    Notes
    -----
    Returns zero vector if the rotation angle is zero.

    Reference
    ---------
    https://en.wikipedia.org/wiki/Rotation_matrix#Conversion_from_rotation_matrix_to_axis–angle

    """
    I = np.eye(3)

    if Q.ndim == 2:
        A = (Q-Q.T)/2.0
        a = np.asarray([A[2, 1], A[0, 2], A[1, 0]])
        sin_t = np.linalg.norm(a)
        cos_t = (np.trace(Q)-1.0)/2.0
        if sin_t == 0.0:
            # Singular cases when Q is symmetric.
            #
            # When cos_t == 1.0, the rotvec is zero.
            #
            # When cos_t == -1.0, the rotation axis is calculated as
            #
            #   np.linalg.norm(Q+I, axis=1)/2
            #
            # and the rotation angle is pi
            #
            # The following line is a generalization for both cases.
            return np.linalg.norm(Q+I, axis=1)*(1.0-cos_t)*np.pi/4
        axis = a/sin_t
        return np.arctan2(sin_t, cos_t)*axis

    if Q.ndim != 3:
        raise ValueError('Q must be either 2D or 3D array')
    
    A = (Q-Q.transpose(0, 2, 1))/2.0
    a = np.column_stack([A[:, 2, 1], A[:, 0, 2], A[:, 1, 0]])
    sin_t = np.linalg.norm(a, axis=1)
    cos_t = (np.trace(Q, axis1=1, axis2=2)-1.0)/2.0
    is_sym = sin_t == 0.0
    rotvec = np.zeros((Q.shape[0], 3))
    rotvec[is_sym] = np.linalg.norm(Q[is_sym]+I, axis=2)*(1.0-cos_t[is_sym])[:, np.newaxis]*np.pi/4
    axis = a[~is_sym]/sin_t[~is_sym, np.newaxis]
    rotvec[~is_sym] = np.arctan2(sin_t[~is_sym], cos_t[~is_sym])[:, np.newaxis]*axis
    return rotvec


def load_bonding_points_from_file():
    """
    Load the center coordinates of the bonding regions defined in `bonding.txt`.

    Returns
    -------
    points : numpy.ndarray, shape=(N, 2)
        Bonding points (xc, yc) coordinates.

    """
    points = []
    with open('bonding.txt', 'r') as f:
        bonding_txt_lines = f.readlines()
    for line in bonding_txt_lines:
        values = line.split()
        if len(values) == 0 or values[0].startswith('#'):
            continue
        if values[0].upper() == 'CIRCLE':
            xc = float(values[1])
            yc = float(values[2])
        elif values[0].upper() == 'RECT':
            x1 = float(values[1])
            y1 = float(values[2])
            x2 = float(values[3])
            y2 = float(values[4])
            xc = 0.5 * (x1 + x2)
            yc = 0.5 * (y1 + y2)
        else:
            raise ValueError('Unknown bonding type: {}'.format(values[0]))
        points.append([xc, yc])
    return np.asarray(points)


def peek_bonding_disp(points_3d, rotvec):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(subplot_kw={'projection': '3d'})
    ax.scatter(points_3d[:, 0], points_3d[:, 1], points_3d[:, 2], color='C0')
    ax.quiver(
        points_3d[:, 0], points_3d[:, 1], points_3d[:, 2],
        rotvec[:, 0], rotvec[:, 1], rotvec[:, 2],
        normalize=False, color='C1',
    )
    ax.set_title('Mapped points with rotation vectors')
    ax.set_xlabel('X')
    ax.set_ylabel('Y')
    ax.set_zlabel('Z')
    ax.axis('equal')
    plt.show()


BONDING_DISP_HEADER = """# Bonding regions displacement data file
#
# This file specifies the displacement and rotation for each bonding region
# listed in `bonding.txt`, following the same order as in that file.
#
# Each line corresponds to a bonding region and contains:
#
#   {U1} {U2} {U3} {UR1} {UR2} {UR3}
#
#   where (U1, U2, U3) are the displacement components, and (UR1, UR2, UR3) are
#   the rotational displacement components (in radians).

"""


if __name__ == '__main__':
    points_2d = load_bonding_points_from_file()
    points_3d, rotvec = my_map(points_2d)

    peek_bonding_disp(points_3d, rotvec)

    with open('bonding_disp.txt', 'w') as f:
        f.write(BONDING_DISP_HEADER)
        for i in range(len(points_2d)):
            u, v = points_2d[i]
            x, y, z = points_3d[i]
            urx, ury, urz = rotvec[i]
            f.write(
                '{:13.6e} {:13.6e} {:13.6e} {:13.6e} {:13.6e} {:13.6e}\n'
                .format(x-u, y-v, z, urx, ury, urz)
            )
    print('Bonding displacement data written to "bonding_disp.txt".')
