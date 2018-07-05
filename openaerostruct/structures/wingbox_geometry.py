from __future__ import division, print_function
import numpy as np

from openmdao.api import ExplicitComponent
from openaerostruct.structures.utils import norm

class WingboxGeometry(ExplicitComponent):
    """
    OpenMDAO component that performs mesh manipulation functions. It reads in
    the initial mesh from the surface dictionary and outputs the altered
    mesh based on the geometric design variables.

    Depending on the design variables selected or the supplied geometry information,
    only some of the follow parameters will actually be given to this component.
    If parameters are not active (they do not deform the mesh), then
    they will not be given to this component.

    Parameters
    ----------
    sweep : float
        Shearing sweep angle in degrees.
    dihedral : float
        Dihedral angle in degrees.
    twist[ny] : numpy array
        1-D array of rotation angles for each wing slice in degrees.
    chord_dist[ny] : numpy array
        Chord length for each panel edge.
    taper : float
        Taper ratio for the wing; 1 is untapered, 0 goes to a point at the tip.

    Returns
    -------
    mesh[nx, ny, 3] : numpy array
        Modified mesh based on the initial mesh in the surface dictionary and
        the geometric design variables.
    """

    def initialize(self):
        self.options.declare('surface', types=dict)

    def setup(self):
        self.surface = self.options['surface']

        self.add_input('mesh', val=self.mesh)

        self.add_output('streamwise_chords', val=np.ones((ny - 1)))
        self.add_output('fem_chords', val=np.ones((ny - 1)))
        self.add_output('fem_twists', val=np.ones((ny - 1)))

        self.declare_partials('*', '*', method='cs')

    def compute(self, inputs, outputs):
        mesh = inputs['mesh']
        vectors = mesh[-1, :, :] - mesh[0, :, :]
        streamwise_chords = np.sqrt(np.sum(vectors**2, axis=1))
        streamwise_chords = 0.5 * streamwise_chords[:-1] + 0.5 * streamwise_chords[1:]

        # Chord lengths for the panel strips at the panel midpoint
        outputs['streamwise_chords'] = streamwise_chords.copy()

        fem_twists = np.zeros(streamwise_chords.shape)
        fem_chords = streamwise_chords.copy()

        surface = self.surface

        # Gets the shear center by looking at the four corners.
        # Assumes same spar thickness for front and rear spar.
        w = (surface['data_x_upper'][0] *(surface['data_y_upper'][0]-surface['data_y_lower'][0]) + \
        surface['data_x_upper'][-1]*(surface['data_y_upper'][-1]-surface['data_y_lower'][-1])) / \
        ( (surface['data_y_upper'][0]-surface['data_y_lower'][0]) + (surface['data_y_upper'][-1]-surface['data_y_lower'][-1]))

        # TODO: perhaps replace this or link with existing nodes computation
        nodes = (1-w) * mesh[0, :, :] + w * mesh[-1, :, :]

        mesh_vectors = mesh[-1, :, :] - mesh[0, :, :]

        # Loop over spanwise elements
        for ielem in range(mesh.shape[1] - 1):

            # Obtain the element nodes
            P0 = nodes[ielem, :]
            P1 = nodes[ielem+1, :]

            elem_vec = (P1 - P0) # vector along element
            temp_vec = elem_vec.copy()
            temp_vec[0] = 0. # vector along element without x component

            # This is used to get chord length normal to FEM element.
            # To be clear, this 3D angle sweep measure.
            # This is the projection to the wing orthogonal to the FEM direction.
            cos_theta_fe_sweep = elem_vec.dot(temp_vec) / norm(elem_vec) / norm(temp_vec)
            fem_chords[ielem] = fem_chords[ielem] * cos_theta_fe_sweep

        outputs['fem_chords'] = fem_chords

        # Loop over spanwise elements
        for ielem in range(mesh.shape[1] - 1):

            # The following is used to approximate the twist angle for the section normal to the FEM element
            mesh_vec_0 = mesh_vectors[ielem]
            temp_mesh_vectors_0 = mesh_vec_0.copy()
            temp_mesh_vectors_0[2] = 0.

            dot_prod_0 = mesh_vec_0.dot(temp_mesh_vectors_0) / norm(mesh_vec_0) / norm(temp_mesh_vectors_0)

            if dot_prod_0 > 1.:
                theta_0 = 0. # to prevent nan in case value for arccos is greater than 1 due to machine precision
            else:
                theta_0 = np.arccos(dot_prod_0)

            mesh_vec_1 = mesh_vectors[ielem + 1]
            temp_mesh_vectors_1 = mesh_vec_1.copy()
            temp_mesh_vectors_1[2] = 0.

            dot_prod_1 = mesh_vec_1.dot(temp_mesh_vectors_1) / norm(mesh_vec_1) / norm(temp_mesh_vectors_1)

            if dot_prod_1 > 1.:
                theta_1 = 0. # to prevent nan in case value for arccos is greater than 1 due to machine precision
            else:
                theta_1 = np.arccos(dot_prod_1)

            fem_twists[ielem] = (theta_0 + theta_1) / 2 * streamwise_chords[ielem] / fem_chords[ielem]

        outputs['fem_twists'] = fem_twists
