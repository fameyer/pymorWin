#!/usr/bin/env python
# vim: set filetype=python:
'''Thermalblock demo.

Usage:
  thermalblock.py [-h] [--estimator-norm=NORM] [--grid=NI]
                  [--help] XBLOCKS YBLOCKS SNAPSHOTS RBSIZE


Arguments:
  XBLOCKS    Number of blocks in x direction.

  YBLOCKS    Number of blocks in y direction.

  SNAPSHOTS  Number of snapshots for basis generation per component.
             In total SNAPSHOTS^(XBLOCKS * YBLOCKS).

  RBSIZE     Size of the reduced basis


Options:
  --estimator-norm=NORM  Norm (trivial, h1) in which to calculate the residual
                         [default: trivial].

  --grid=NI              Use grid with 2*NI*NI elements [default: 60].

  -h, --help             Show this message.
'''
from __future__ import absolute_import, division, print_function
import sys
from docopt import docopt
import time
from functools import partial
import math as m
import numpy as np
from PySide import QtGui
from OpenGL.GL import *
import OpenGL.GL as gl
from PySide import QtOpenGL
from PySide.QtOpenGL import QGLShader, QGLShaderProgram

import pymor.core as core
core.logger.MAX_HIERACHY_LEVEL = 2
from pymor.analyticalproblems import ThermalBlockProblem
from pymor.discretizers import discretize_elliptic_cg
from pymor.reductors.linear import reduce_stationary_affine_linear
from pymor.algorithms import greedy, gram_schmidt_basis_extension
from pymor.parameters.base import Parameter

core.getLogger('pymor.algorithms').setLevel('DEBUG')
core.getLogger('pymor.discretizations').setLevel('DEBUG')

PARAM_STEPS = 10
PARAM_MIN = 0.1
PARAM_MAX = 1


def compile_vertex_shader(source):
    """Compile a vertex shader from source."""
    vertex_shader = gl.glCreateShader(gl.GL_VERTEX_SHADER)
    gl.glShaderSource(vertex_shader, source)
    gl.glCompileShader(vertex_shader)
    # check compilation error
    result = gl.glGetShaderiv(vertex_shader, gl.GL_COMPILE_STATUS)
    if not(result):
        raise RuntimeError(gl.glGetShaderInfoLog(vertex_shader))
    return vertex_shader

def link_shader_program(vertex_shader):
    """Create a shader program with from compiled shaders."""
    program = gl.glCreateProgram()
    gl.glAttachShader(program, vertex_shader)
    gl.glLinkProgram(program)
    # check linking error
    result = gl.glGetProgramiv(program, gl.GL_LINK_STATUS)
    if not(result):
        raise RuntimeError(gl.glGetProgramInfoLog(program))
    return program

VS = """
#version 330
// Attribute variable that contains coordinates of the vertices.
layout(location = 0) in vec3 position;
 
// Main function, which needs to set `gl_Position`.
void main()
{
    float x = position.z;
    float blue = min(max(4 * (0.75 - x), 0.), 1.);
    float red = min(max(4 * (x - 0.25), 0.), 1.);
    float green = min(max(4 * abs(x - 0.5) - 1., 0.), 1.);
    gl_Position = vec4(position.x-0.5, position.y-0.5, 0., 0.5);
    gl_FrontColor = vec4(red, green, blue, 1);
}
"""
class SolutionWidget(QtOpenGL.QGLWidget):

    def __init__(self, parent, sim):
        super(SolutionWidget, self).__init__(parent)
        self.setMinimumSize(300, 300)
        self.sim = sim
        self.dl = 1
        self.U = np.ones(sim.grid.size(2))
        self.set(self.U)

    def resizeGL(self, w, h):
        # Prevent A Divide By Zero If The Window Is Too Small
        h = max(1, h)
        glViewport(0, 0, w, h)
        self.set(self.U)

    def initializeGL(self):
        glClearColor(1.0, 1.0, 1.0, 1.0)
        glShadeModel(GL_SMOOTH)
        self.shaders_program = link_shader_program(compile_vertex_shader(VS))

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT)
        glCallList(self.dl)
        gl.glUseProgram(self.shaders_program)

    def set(self, U):
        vmin = np.min(U)
        vmax = np.max(U)
        U -= vmin
        U /= float(vmax - vmin)
        self.U = U
        glNewList(self.dl, GL_COMPILE)
        h = self.size().height()
        w = self.size().width()
        glViewport(0, 0, w, h)
        glLoadIdentity()

        g = self.sim.grid
        glScalef(2, 2, 1)
        glTranslatef(-0.5, -0.5, 0)
        pos_x = g.centers(2)[:, 0]
        pos_y = g.centers(2)[:, 1]

        glBegin(GL_TRIANGLES)
        glNormal3f(0, 0, -1)
        for c in g.subentities(0, 2):
            for i in c:
                glVertex3f(pos_x[i], pos_y[i], self.U[i])
        glEnd()
        glEndList()
        self.update()

class ParamRuler(QtGui.QWidget):
    def __init__(self, parent, sim):
        super(ParamRuler, self).__init__(parent)
        self.sim = sim
        self.setMinimumSize(200, 100)
        box = QtGui.QGridLayout()
        self.spins = []
        for i in xrange(args['XBLOCKS']):
            for j in xrange(args['YBLOCKS']):
                spin = QtGui.QDoubleSpinBox()
                spin.setRange(PARAM_MIN, PARAM_MAX)
                spin.setSingleStep((PARAM_MAX - PARAM_MIN) / PARAM_STEPS)
                spin.setValue(PARAM_MIN)
                self.spins.append(spin)
                box.addWidget(spin, i, j)
                spin.valueChanged.connect(parent.solve_update)
        self.setLayout(box)

    def enable(self, enable=True):
        for spin in self.spins:
            spin.isEnabled = enable

class SimPanel(QtGui.QWidget):
    def __init__(self, parent, sim):
        super(SimPanel, self).__init__(parent)
        self.sim = sim
        box = QtGui.QHBoxLayout()
        self.solution = SolutionWidget(self, self.sim)
#        box.addStretch()
        box.addWidget(self.solution, 2)

        self.param_panel = ParamRuler(self, sim)
        box.addWidget(self.param_panel)
        self.setLayout(box)

    def solve_update(self):
        tic = time.time()
        self.param_panel.enable(False)
        args = self.sim.args
        shape = (args['XBLOCKS'], args['YBLOCKS'])
        mu = Parameter({'diffusion': np.array([s.value() for s in self.param_panel.spins]).reshape(shape)})
        U = self.sim.solve(mu)
        print('Simtime {}'.format(time.time() - tic))
        tic = time.time()
        self.solution.set(U)
        self.param_panel.enable(True)
        print('Drawtime {}'.format(time.time() - tic))


class AllPanel(QtGui.QWidget):
    def __init__(self, parent, reduced_sim, detailed_sim):
        super(AllPanel, self).__init__(parent)

        box = QtGui.QVBoxLayout()
        box.addWidget(SimPanel(self, reduced_sim))
        box.addWidget(SimPanel(self, detailed_sim))
        self.setLayout(box)


class RBGui(QtGui.QMainWindow):
    def __init__(self, args):
        super(RBGui, self).__init__()
        args['XBLOCKS'] = int(args['XBLOCKS'])
        args['YBLOCKS'] = int(args['YBLOCKS'])
        args['--grid'] = int(args['--grid'])
        args['SNAPSHOTS'] = int(args['SNAPSHOTS'])
        args['RBSIZE'] = int(args['RBSIZE'])
        args['--estimator-norm'] = args['--estimator-norm'].lower()
        assert args['--estimator-norm'] in {'trivial', 'h1'}
        reduced = ReducedSim(args)
        detailed = DetailedSim(args)
        panel = AllPanel(self, reduced, detailed)
        self.setCentralWidget(panel)


class SimBase(object):
    def __init__(self, args):
        self.args = args
        self.first = True
        self.problem = ThermalBlockProblem(num_blocks=(args['XBLOCKS'], args['YBLOCKS']),
                                           parameter_range=(PARAM_MIN, PARAM_MAX))
        self.discretization, pack = discretize_elliptic_cg(self.problem, diameter=m.sqrt(2) / args['--grid'])
        self.grid = pack['grid']


class ReducedSim(SimBase):

    def __init__(self, args):
        super(ReducedSim, self).__init__(args)

    def _first(self):
        args = self.args
        error_product = self.discretization.h1_product if args['--estimator-norm'] == 'h1' else None
        reductor = partial(reduce_stationary_affine_linear, error_product=error_product)

        greedy_data = greedy(self.discretization, reductor,
                             self.discretization.parameter_space.sample_uniformly(args['SNAPSHOTS']),
                             use_estimator=True, error_norm=self.discretization.h1_norm,
                             extension_algorithm=gram_schmidt_basis_extension, max_extensions=args['RBSIZE'])
        self.rb_discretization, self.reconstructor = greedy_data['reduced_discretization'], greedy_data['reconstructor']
        self.first = False

    def solve(self, mu):
        if self.first:
            self._first()
        return self.reconstructor.reconstruct(self.rb_discretization.solve(mu))


class DetailedSim(SimBase):

    def __init__(self, args):
        super(DetailedSim, self).__init__(args)

    def solve(self, mu):
        return self.discretization.solve(mu)


if __name__ == '__main__':
    app = QtGui.QApplication(sys.argv)
    args = docopt(__doc__)
    win = RBGui(args)
    win.show()
    sys.exit(app.exec_())