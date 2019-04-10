'''
Solve for trimmed flight solution of CRM geometry using Newton method.
Print out lift, drag and moment coefficient when complete. Check output
directory for Tecplot solution files.
'''
from __future__ import division, print_function
import numpy as np

from openaerostruct.geometry.utils import plot3D_meshes
from openaerostruct.geometry.geometry_group import Geometry
from openaerostruct.aerodynamics.aero_groups import AeroPoint

from openmdao.api import IndepVarComp, Problem
import os

# Specify output directory
output_dir = './Outputs/'
# If directory does not exist, then create it
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

plot3dFile = './Inputs/crm.xyz'
meshes = plot3D_meshes(plot3dFile, 1e-8)

# Create list to store all VLM surfaces we are about to add
surfaces = []

# Skip the vertical tail and vertical fuselage panel for now,
# (they don't do anything symmetric flow anyways)
dont_include = ['Fuselage_V', 'Tail_V']

default_dict = {
            'name' : '',        # name of the surface
            'symmetry' : True,     # if true, model one half of wing
                                    # reflected across the plane y = 0
            'S_ref_type' : 'projected', # how we compute the wing area,
                                     # can be 'wetted' or 'projected

            # Aerodynamic performance of the lifting surface at
            # an angle of attack of 0 (alpha=0).
            # These CL0 and CD0 values are added to the CL and CD
            # obtained from aerodynamic analysis of the surface to get
            # the total CL and CD.
            # These CL0 and CD0 values do not vary wrt alpha.
            'CL0' : 0.0,            # CL of the surface at alpha=0
            'CD0' : 0.00,            # CD of the surface at alpha=0

            # Airfoil properties for viscous drag calculation
            'k_lam' : 0.05,         # percentage of chord with laminar
                                    # flow, used for viscous drag
            't_over_c_cp' : np.array([0.15]),      # thickness over chord ratio (NACA0015)
            'c_max_t' : .303,       # chordwise location of maximum (NACA0015)
                                    # thickness
            'with_viscous' : False,  # if true, compute viscous drag
            'with_wave' : False,     # if true, compute wave drag
            'flexible':False,
            't_over_c' : 0.15,      # thickness over chord ratio (NACA0015)
            'c_max_t' : .303,       # chordwise location of maximum (NACA0015)
            'Cl_max': 1.2,
            'claf' : 1.0, # Lift curve slope multiplier, based on xfoil
            }

# Loop through all the meshes we just loaded and create an input dict for each
for surf_name in meshes:
    surf_dict = default_dict.copy()

    mesh = meshes[surf_name]

    surf_dict['name'] = surf_name
    surf_dict['mesh'] = mesh

    if surf_name == 'Tail_H':
        # Set one twist variable on tail to control incidence for trim
        surf_dict['twist_cp'] = np.zeros(1)

    if surf_name not in dont_include:
        surfaces.append(surf_dict)

# Create the problem and the model group
prob = Problem()

# Define flight variables as independent variables of the model
indep_var_comp = IndepVarComp()
indep_var_comp.add_output('v', val=248.136, units='m/s')
indep_var_comp.add_output('alpha', val=5., units='deg')
indep_var_comp.add_output('beta', val=0., units='deg')
indep_var_comp.add_output('M', val=0.84)
indep_var_comp.add_output('re', val=1.e6, units='1/m')
indep_var_comp.add_output('rho', val=0.38, units='kg/m**3')
indep_var_comp.add_output('cg', val=np.array([33.68, 0.0, 4.52]), units='m')
indep_var_comp.add_output('S_ref_total', val=383.7, units='m**2')
indep_var_comp.add_output('Omega', val=np.array([0.0, 0.0, 0.0]), units='deg/s')

prob.model.add_subsystem('prob_vars',
    indep_var_comp,
    promotes=['*'])

# Loop over each surface in the surfaces list
for surface in surfaces:

    geom_group = Geometry(surface=surface)

    # Add tmp_group to the problem as the name of the surface.
    # Note that is a group and performance group for each
    # individual surface.
    prob.model.add_subsystem(surface['name'], geom_group)

# Create the aero point group and add it to the model
aero_group = AeroPoint(surfaces=surfaces, output_dir=output_dir,
                           user_specified_Sref=True, compressible=True)
point_name = 'aero_point_0'
prob.model.add_subsystem(point_name, aero_group, promotes_inputs=['*'])

# Set up the problem
prob.setup()

# Specify target lift and y-moment coefficients
CL_target = 0.5
CM_target = 0

# Perform Newton solve to find trim CL solution
target = np.zeros(2)
error = np.ones(2)*1e-3
Jac = np.zeros([2,2])
tol = 1e-3
iter = 0
while np.linalg.norm(error)>tol:
    # Evaluate current iteration
    prob.run_model()
    error[0] = CL_target - prob[point_name+'.CL'][0]
    error[1] = CM_target - prob[point_name+'.CM'][1]
    print(iter, error, [prob['alpha'], prob['Tail_H.twist_cp']])

    # Compute Jacobian for Newton solve
    fsens = prob.compute_totals(of=[point_name+'.CL',point_name+'.CM'],
        wrt=['Tail_H.twist_cp', 'alpha'])
    Jac[0,0] = fsens[point_name+'.CL', 'alpha']
    Jac[0,1] = fsens[point_name+'.CL', 'Tail_H.twist_cp']
    Jac[1,0] = fsens[point_name+'.CM', 'alpha'][1]
    Jac[1,1] = fsens[point_name+'.CM', 'Tail_H.twist_cp'][1]

    # Perform Newton solve
    delta = np.linalg.solve(Jac, error)

    # Perform Newton update
    prob['alpha'] += delta[0]
    prob['Tail_H.twist_cp'] += delta[1]

    iter += 1

# Run final analysis
prob.run_model()

# Print solution
print('CD', prob[point_name+'.CD'][0])
print('CL', prob[point_name+'.CL'][0])
print('CM[0]', prob[point_name+'.CM'][0])
print('CM[1]', prob[point_name+'.CM'][1])
print('CM[2]', prob[point_name+'.CM'][2])

# Write out resulting aircraft to AVL input file
aero_group.write_AVL(output_dir+'crm.avl')
