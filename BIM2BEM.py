
import ifcopenshell
import ifcopenshell.geom as geom
from skgeom import *
import skgeom
import pyclipper
import math
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components

def get_unit_normal_plane(points):
  plane = skgeom.Plane3(points[0], points[1], points[2])
  
  normal = plane.orthogonal_vector()
  length = math.sqrt(normal.squared_length())
  
  return skgeom.Plane3(points[0], normal / length)

def are_equal(plane_a, plane_b):
  normal_a = plane_a.orthogonal_vector()
  normal_b = plane_b.orthogonal_vector()
  
  if not abs(float(normal_a * normal_b - 1)) < 1e-6: return False
  
  if not abs(float(plane_a.d() - plane_b.d())) < 1e-6: return False

  return True

SCALING_FACTOR = 1e4

def get_poly_tree(plane, points):
  poly_tree = pyclipper.PyPolyNode()
  
  polygon2 = skgeom.Polygon(list(map(lambda point: plane.to_2d(point), points)))
  poly_tree.Contour = list(map(lambda coord: [int(SCALING_FACTOR * coord[0]), int(SCALING_FACTOR * coord[1])] , polygon2.coords))
  poly_tree.IsOpen = True
  
  return poly_tree

def get_clipper(subject, clip):  
  clipper = pyclipper.Pyclipper()
    
  clipper.AddPaths(subject, pyclipper.PT_SUBJECT, True)
  clipper.AddPaths(clip, pyclipper.PT_CLIP, True)
  
  return clipper

def execute_clipping(clipper, type):
  return clipper.Execute2(type, pyclipper.PFT_EVENODD, pyclipper.PFT_EVENODD)

def clipping(subject, clip, boolean_operation):
  if not subject.Contour and not subject.Childs:
    if boolean_operation == "join": return clip
    if boolean_operation == "intersection": return subject
    if boolean_operation == "difference": return subject
    return clip

  if not clip.Contour and not clip.Childs:
    if boolean_operation == "join": return subject
    if boolean_operation == "intersection": return clip
    if boolean_operation == "difference": return subject
    return subject
  
  clipper = get_clipper(pyclipper.PolyTreeToPaths(subject), pyclipper.PolyTreeToPaths(clip))

  if boolean_operation == "join": return execute_clipping(clipper, pyclipper.CT_UNION)
  if boolean_operation == "intersection": return execute_clipping(clipper, pyclipper.CT_INTERSECTION)
  if boolean_operation == "difference": return execute_clipping(clipper, pyclipper.CT_DIFFERENCE)
  
  union = execute_clipping(clipper, pyclipper.CT_UNION)
  intersection = execute_clipping(clipper, pyclipper.CT_INTERSECTION)
  
  if not intersection.Contour and not intersection.Childs:
    return union
  
  clipper = get_clipper(pyclipper.PolyTreeToPaths(union), pyclipper.PolyTreeToPaths(intersection))
  
  return execute_clipping(clipper, pyclipper.CT_DIFFERENCE)
  
settings = ifcopenshell.geom.settings()
settings.set(settings.USE_WORLD_COORDS, True)

ifc_file = ifcopenshell.open('./test.ifc')

building_element2poly_trees = {}
for building_element in ifc_file.by_type('IfcBuildingElement'):
  if not (building_element.is_a('IfcWall') or building_element.is_a('IfcSlab')): continue
    
  shape = ifcopenshell.geom.create_shape(settings, building_element)
  geo = shape.geometry
  vertices = geo.verts
  faces = geo.faces

  plane2poly_trees = {}
  for f in range(0, len(faces), 3):
    points = []
    for v in faces[f : f + 3]:
      points.append(skgeom.Point3(vertices[3*v], vertices[3*v+1], vertices[3*v+2]))
    plane = get_unit_normal_plane(points)

    is_opposite = False
    poly_trees = [pyclipper.PyPolyNode(), pyclipper.PyPolyNode()]
    for building_element_plane, building_element_poly_trees in plane2poly_trees.items():
      is_opposite = are_equal(building_element_plane, plane.opposite())
      if not (are_equal(building_element_plane, plane) or is_opposite): continue
      
      plane = building_element_plane
      poly_trees = building_element_poly_trees
      break
    index = (0,1)[is_opposite]
    poly_trees[index] = clipping(poly_trees[index], get_poly_tree(plane, points), "join")

    plane2poly_trees[plane] = poly_trees
  
  building_element2poly_trees[building_element] = plane2poly_trees

# for building_element, plane2poly_trees in building_element2poly_trees.items():
  # print(building_element)
  # for plane, poly_trees in plane2poly_trees.items():
    # print(plane)
    # poly_tree = clipping(poly_trees[0], poly_trees[1], "symmetric_difference")
    # for polygon2 in pyclipper.PolyTreeToPaths(poly_tree):
      # print(list(map(lambda coord: plane.to_3d(skgeom.Point2(coord[0] / SCALING_FACTOR, coord[1] / SCALING_FACTOR)), polygon2)))

# print(hola)
      
plane2poly_tree = {}
for building_element, plane2poly_trees in building_element2poly_trees.items():
  for plane, poly_trees in plane2poly_trees.items():
    poly_tree = clipping(poly_trees[0], poly_trees[1], "symmetric_difference")
    for global_plane, global_poly_tree in plane2poly_tree.items():
      is_opposite = are_equal(global_plane, plane.opposite())
      if not (are_equal(global_plane, plane) or is_opposite): continue
      
      poly_tree = clipping(global_poly_tree, poly_tree, "symmetric_difference")
      plane = global_plane
      break
        
    plane2poly_tree[plane] = poly_tree
    
# count = 0
# for plane, poly_tree in plane2poly_tree.items():
  # print(count)
  # print(plane)
  # for polygon2 in pyclipper.PolyTreeToPaths(poly_tree):
    # print(list(map(lambda coord: plane.to_3d(skgeom.Point2(coord[0] / SCALING_FACTOR, coord[1] / SCALING_FACTOR)), polygon2)))
  # print("")
  # count += 1

# print(hola)

def path2polygon3(path, plane):
  return list(map(lambda coord: plane.to_3d(skgeom.Point2(coord[0] / SCALING_FACTOR, coord[1] / SCALING_FACTOR)), path))

def add_polygon3s(poly_tree, plane, firsts):
  contour = poly_tree.Contour
  if not contour:
    for child in poly_tree.Childs: add_polygon3s(child, plane, firsts)
  else:
    outer_boundary = path2polygon3(contour, plane)
    holes = list(map(lambda hole: path2polygon3(hole.Contour, plane), poly_tree.Childs))
    
    firsts.append([plane, outer_boundary, holes])
    
    for hole in poly_tree.Childs: 
      for child in hole.Childs: add_polygon3s(child, plane, firsts)

firsts = []
for plane, poly_tree in plane2poly_tree.items():
  add_polygon3s(poly_tree, plane, firsts)
  
# for polygon3 in firsts:
  # print(polygon3)
  
def has_on_plane(plane, point):
  normal = plane.orthogonal_vector()
  distance = normal * (point - skgeom.Point3(0, 0, 0)) + plane.d()
  
  return abs(float(distance)) < 1e-3

def get_segment3s(paths, plane):
  segment3s = []
  
  for path in paths:
    prev_point3 = path[-1]
    has_prev_point3 = has_on_plane(plane, prev_point3)
    for point3 in path:
      if has_on_plane(plane, point3):
        if has_prev_point3: segment3s.append(skgeom.Segment3(point3, prev_point3))
        has_prev_point3 = True
      else:
        has_prev_point3 = False
      prev_point3 = point3
  
  return segment3s

def inner_product(vector2_i, vector2_j):
  return vector2_i.x() * vector2_j.x() + vector2_i.y() * vector2_j.y()
  
def polygons3_do_intersect(polygon3_i, polygon3_j):      
  segment3s_i = get_segment3s(([polygon3_i[1]] + polygon3_i[2]), polygon3_j[0])
  if not segment3s_i: return False
  plane_i = polygon3_i[0]
  segment3s_j = get_segment3s(([polygon3_j[1]] + polygon3_j[2]), plane_i)
  if not segment3s_j: return False
  
  for segment3_i in segment3s_i:
    segment2_i = skgeom.Segment2(plane_i.to_2d(segment3_i.source()), plane_i.to_2d(segment3_i.target()))
    
    point2_i = segment2_i.min()
    vector2_i = segment2_i.to_vector()
    vector2_i /= vector2_i.squared_length()
    
    max_i = inner_product(vector2_i, segment2_i.max() - point2_i)
    for segment3_j in segment3s_j:
      segment2_j = skgeom.Segment2(plane_i.to_2d(segment3_j.source()), plane_i.to_2d(segment3_j.target()))

      min_j = inner_product(vector2_i, segment2_j.min() - point2_i)
      max_j = inner_product(vector2_i, segment2_j.max() - point2_i)

      if max_j > 0.0 and max_i > min_j: return True
  
  return False

row = []
col = []
data = []
for id_polygon_i, polygon3_i in enumerate(firsts):
  for id_polygon_j, polygon3_j in enumerate(firsts[id_polygon_i+1:]):
    if not polygons3_do_intersect(polygon3_i, polygon3_j): continue
    
    row.append(id_polygon_i)
    col.append(id_polygon_j+id_polygon_i+1)
    data.append(1)
    
n_components, labels = connected_components(csgraph=csr_matrix((np.array(data), (np.array(row), np.array(col))), shape=(len(firsts), len(firsts))), directed=False, return_labels=True)

owner_history = ifc_file.by_type("IfcOwnerHistory")[0]
context = ifc_file.by_type("IfcGeometricRepresentationContext")[0]

for i in range(0, n_components):
  building_storey = None
  items = []
  
  for id, first in enumerate(firsts):
    if not labels[id] == i: continue
    
    first_plane = first[0]
        
    first_poly_tree = get_poly_tree(first_plane, first[1])
    first_poly_tree.depth = 1
    
    for hole in first[2]:
      hole_poly_tree = get_poly_tree(first_plane, hole)
      
      hole_poly_tree.Parent = first_poly_tree
      hole_poly_tree.IsHole = True
      hole_poly_tree.depth = 1
      first_poly_tree.depth = 2
    
    for building_element, plane2poly_trees in building_element2poly_trees.items():
      for plane, poly_trees in plane2poly_trees.items():
        for index, poly_tree in enumerate(poly_trees):
          is_opposite = are_equal(first_plane, opposite_plane)
          if not (are_equal(global_plane, plane) or is_opposite): continue
          
          if clipping(first_poly_tree, poly_trees[0], "intersection").Contour.Area < 1e-6: continue
          
          if building_element.is_a('IfcWall'): building_storey = building_element.ContainedInStructure[0].RelatingStructure
  
  axis2placement = create_ifcaxis2placement(ifc_file, point, dir1, dir2)
  placement = ifc_file.createIfcLocalPlacement(building_storey, axis2placement)
  
  ifc_file.createIfcLocalPlacement(ifcfile, relative_to=storey_placement)
          if index == 1: plane.opposite
          
        if clipping(first_poly_tree, poly_trees[0], "intersection").Contour.Area < 1e-6: continue
        
    for building_element, building_element_plane2poly_tree in building_element2poly_treee.items():
      for plane, building_poly_tree in building_element_plane2poly_tree.items():
        
        
        space_boundary_poly_tree = clipping(building_poly_tree, translate_poly_tree(first_poly_tree, None, first_plane, plane, is_opposite), "intersection")

  ifc_file.createIfcShapeRepresentation(context, "Body", "Brep", items)

# https://github.com/IfcOpenShell/IfcOpenShell/blob/fcc2b9ee13e0505c617b306fe5e29890855ced5e/src/ifcblenderexport/blenderbim/bim/export_ifc.py#L3357
# https://github.com/IfcOpenShell/IfcOpenShell/blob/fcc2b9ee13e0505c617b306fe5e29890855ced5e/src/ifcblenderexport/blenderbim/bim/export_ifc.py#L1925