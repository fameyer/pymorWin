# -*- coding: utf-8 -*-
# This file is part of the pyMOR project (http://www.pymor.org).
# Copyright Holders: Rene Milk, Stephan Rave, Felix Schindler
# License: BSD 2-Clause License (http://opensource.org/licenses/BSD-2-Clause)
#
# Contributors: Michael Laier <m_laie01@uni-muenster.de>

from __future__ import absolute_import, division, print_function

from itertools import product

from pymor.analyticalproblems.elliptic import EllipticProblem
from pymor.core import Unpicklable
from pymor.domaindescriptions.basic import RectDomain
from pymor.functions.basic import ConstantFunction
from pymor.functions.interfaces import FunctionInterface
from pymor.parameters.functionals import ProjectionParameterFunctional
from pymor.parameters.spaces import CubicParameterSpace


class ThermalBlockProblem(EllipticProblem, Unpicklable):
    """Analytical description of a 2D thermal block diffusion problem.

    This problem is to solve the elliptic equation ::

      - ∇ ⋅ [ d(x, μ) ∇ u(x, μ) ] = f(x, μ)

    on the domain [0,1]^2 with Dirichlet zero boundary values. The domain is
    partitioned into nx x ny blocks and the diffusion function d(x, μ) is
    constant on each such block (i,j) with value μ_ij. ::

           ----------------------------
           |        |        |        |
           |  μ_11  |  μ_12  |  μ_13  |
           |        |        |        |
           |---------------------------
           |        |        |        |
           |  μ_21  |  μ_22  |  μ_23  |
           |        |        |        |
           ----------------------------

    The Problem is implemented as an |EllipticProblem| with the
    characteristic functions of the blocks as `diffusion_functions`.

    Parameters
    ----------
    num_blocks
        The tuple (nx, ny)
    parameter_range
        A tuple (μ_min, μ_max). Each |Parameter| component μ_ij is allowed
        to lie in the interval [μ_min, μ_max].
    rhs
        The |Function| f(x, μ).
    """

    def __init__(self, num_blocks=(3, 3), parameter_range=(0.1, 1), rhs=ConstantFunction(dim_domain=2)):

        domain = RectDomain()
        parameter_space = CubicParameterSpace({'diffusion': (num_blocks[1], num_blocks[0])}, *parameter_range)
        dx = 1 / num_blocks[0]
        dy = 1 / num_blocks[1]

        def parameter_functional_factory(x, y):
            return ProjectionParameterFunctional(component_name='diffusion',
                                                 component_shape=(num_blocks[1], num_blocks[0]),
                                                 coordinates=(num_blocks[1] - y - 1, x),
                                                 name='diffusion_{}_{}'.format(x, y))

        diffusion_functions = tuple(ThermalBlockDiffusionFunction(x, y, dx, dy)
                                    for x, y in product(xrange(num_blocks[0]), xrange(num_blocks[1])))
        parameter_functionals = tuple(parameter_functional_factory(x, y)
                                      for x, y in product(xrange(num_blocks[0]), xrange(num_blocks[1])))

        super(ThermalBlockProblem, self).__init__(domain, rhs, diffusion_functions, parameter_functionals,
                                                  name='ThermalBlock')
        self.parameter_space = parameter_space
        self.parameter_range = parameter_range
        self.num_blocks = num_blocks


class ThermalBlockDiffusionFunction(FunctionInterface):

    dim_domain = 2
    shape_range = tuple()

    def __init__(self, x, y, dx, dy):
        self.x = x
        self.y = y
        self.dx = dx
        self.dy = dy

    def evaluate(self, x, mu=None):
        return (1. * (x[..., 0] >= self.x * self.dx) * (x[..., 0] < (self.x + 1) * self.dx)
                   * (x[..., 1] >= self.y * self.dy) * (x[..., 1] < (self.y + 1) * self.dy))
