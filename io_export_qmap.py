# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# ##### END GPL LICENSE BLOCK #####

bl_info = {
    "name": "Export Quake Map (.map)",
    "author": "chedap",
    "version": (2022, 8, 27),
    "blender": (3, 2, 2),
    "location": "File > Import-Export",
    "description": "Export geometry as brushes",
    "category": "Import-Export",
    "tracker_url": "https://github.com/c-d-a/io_export_qmap"
}

import bpy, bmesh, math, time
from mathutils import Vector, Matrix, geometry
from numpy.linalg import solve
from bpy_extras.io_utils import ExportHelper
from bpy.props import *

class ExportQuakeMap(bpy.types.Operator, ExportHelper):
    bl_idname = 'export.map'
    bl_label = bl_info['name']
    bl_description = bl_info['description']
    bl_options = {'UNDO'}
    filename_ext = ".map"
    filter_glob: StringProperty(default="*.map", options={'HIDDEN'})

    option_sel: BoolProperty(name="Selection only", default=True)
    option_tm: BoolProperty(name="Apply transform", default=True)
    option_tj: BoolProperty(name="Triangulate 180°", default=True)
    option_geo: EnumProperty(name="Geo", default='Faces',
        items=( ('Brush', "Brush", "Export each object as a single brush"),
                ('Faces', "Faces", "Export each face as a pyramid brush"),
                ('Prisms', "Walls", "Export each face as a prism brush"),
                ('Soup', "Terrain", "Export faces as poly-soup extruded on Z"),
                ('Blob', "Blob", "Export as pyramids with a common apex") ) )
    option_grid: FloatProperty(name="Grid", default=1.0,
        description="Snap to grid (0 for off-grid)", min=0.0, max=256.0)
    option_depth: FloatProperty(name="Depth", default=2.0,
        description="Pyramid poke offset", min=0.0, max=256.0)
    option_group: EnumProperty(name="Name", default='Gen',
        items=( ('None', "None", "Export loose worldspawn brushes"),
                ('Auto', "Blender", "Use Blender name"),
                ('Gen', "Generic", "Use generic name") ) )
    option_brush: EnumProperty(name="Planes", default='Quake',
        items=( ('Quake', "Quake", "Brush planes as three vertices"),
                ('Doom3', "Doom 3", "Brush planes as normal + distance") ) )
    option_uv: EnumProperty(name="UVs", default='Valve',
        items=( ('Quake', "Standard", "Axis-aligned texture projection"),
                ('Valve', "Valve220", "Edge-bound texture projection"),
                ('BPrim', "Primitives", "Plane-bound texture projection") ) )
    option_flags: EnumProperty(name="Flags", default='None',
        items=( ('None', "None", "No flags"),
                ('Q2', "Quake 2", "Content, Surface, Value") ) )
    option_dest: EnumProperty(name="Save to", default='File',
        items=( ('File', "File", "Write data to a .map file"),
                ('Clip', "Clipboard", "Store data in system buffer") ) )
    option_skip: StringProperty(name="Generic material", default='skip',
        description="Material to use on new and unassigned faces")
    option_gname: StringProperty(name="Generic name", default='func_group',
        description="Classname for brush entities, unless set otherwise")
    option_fp: IntProperty(name="Precision", default=5,
        description="Number of significant digits", min=0, soft_max=17)
    seen_names = []


    def entname(self, ent):
        if self.option_group == 'None':
            return ''
        elif self.option_group == 'Gen':
            tname = self.option_gname
        elif self.option_group == 'Auto':
            tname = ent.name.rstrip('0123456789')
            tname = tname[:-1] if tname[-1] in ('.',' ') else ent.name

        name = '}\n{\n"classname" "' + tname + '"\n'
        if self.option_brush == 'Doom3':
            self.seen_names.append(tname)
            n_name = self.seen_names.count(tname)
            name += '"name" "' + tname + f'_{n_name}"\n'
            name += '"model" "' + tname + f'_{n_name}"\n'
        return name


    def gridsnap(self, vector):
        grid = self.option_grid
        if grid:
            return [round(co/grid)*grid for co in vector]
        else:
            return vector


    def printvec(self, vector):
        return ' '.join([f'{co:.{self.option_fp}g}' for co in vector])


    def brushplane(self, face):
        if self.option_brush == 'Quake':
            planestring = ""
            for vert in reversed(face.verts[0:3]):
                planestring += f'( {self.printvec(vert.co)} ) '
            return planestring
        elif self.option_brush == 'Doom3':
            # more accurate than just the dot product
            dist = geometry.distance_point_to_plane(
                                    (.0,.0,.0), face.verts[0].co, face.normal)
            return f'( {self.printvec([co for co in face.normal] + [dist])} ) '


    def faceflags(self, obj):
        if self.option_flags == 'None':
            return "\n"
        elif self.option_flags == 'Q2':
            col = obj.users_collection[0]
            if ('detail' in obj.name) or ('detail' in col.name):
                return f" {1<<27} 0 0\n"
            else:
                return " 0 0 0\n"


    def texdata(self, face, mesh, obj):
        mat = None
        width = height = 64
        if obj.material_slots:
            mat = obj.material_slots[face.material_index].material
        if mat:
            if mat.node_tree:
                for node in mat.node_tree.nodes:
                    if node.type == 'TEX_IMAGE':
                        if node.image.has_data:
                            width, height = node.image.size
                            break
            texstring = mat.name.replace(" ","_")
        else:
            texstring = self.option_skip
        if self.option_brush == 'Doom3':
            texstring = f'"{texstring}"'

        V = [loop.vert.co for loop in face.loops]
        uv_layer = mesh.loops.layers.uv.active
        if uv_layer is None:
            uv_layer = mesh.loops.layers.uv.new("dummy")
        T = [loop[uv_layer].uv for loop in face.loops]

        if self.option_uv == 'Valve':
            # [ Ux Uy Uz Uoffs ] [ Vx Vy Vz Voffs ] rotation scaleU scaleV
            dummy = ' [ 1 0 0 0 ] [ 0 -1 0 0 ] 0 1 1'

            height = -height # v is flipped

            # ported from: https://bitbucket.org/khreathor/obj-2-map
            # Set up "2d world" coordinate system with the 01 edge along X
            world01 = V[1] - V[0]
            world02 = V[2] - V[0]
            world01_02Angle = world01.angle(world02)
            if face.normal.dot(world01.cross(world02)) < 0:
                world01_02Angle = -world01_02Angle
            world01_2d = Vector((world01.length, 0.0))
            world02_2d = Vector((math.cos(world01_02Angle),
                                math.sin(world01_02Angle))) * world02.length

            # Get 01 and 02 vectors in UV space and scale them
            tex01 = T[1] - T[0]
            tex02 = T[2] - T[0]
            tex01.x *= width
            tex02.x *= width
            tex01.y *= height
            tex02.y *= height

            '''
            a = world01_2d
            b = world02_2d
            p = tex01
            q = tex02

            [ px ]   [ m11 m12 0 ] [ ax ]
            [ py ] = [ m21 m22 0 ] [ ay ]
            [ 1  ]   [ 0   0   1 ] [ 1  ]

            [ qx ]   [ m11 m12 0 ] [ bx ]
            [ qy ] = [ m21 m22 0 ] [ by ]
            [ 1  ]   [ 0   0   1 ] [ 1  ]

            px = ax * m11 + ay * m12
            py = ax * m21 + ay * m22
            qx = bx * m11 + by * m12
            qy = bx * m21 + by * m22

            [ px ]   [ ax ay 0  0  ] [ m11 ]
            [ py ] = [ 0  0  ax ay ] [ m12 ]
            [ qx ]   [ bx by 0  0  ] [ m21 ]
            [ qy ]   [ 0  0  bx by ] [ m22 ]
            '''

            # Find an affine transformation to convert
            # world01_2d and world02_2d to their respective UV coords
            texCoordsVec = Vector((tex01.x, tex01.y, tex02.x, tex02.y))
            world2DMatrix = Matrix(((world01_2d.x, world01_2d.y, 0, 0),
                                    (0, 0, world01_2d.x, world01_2d.y),
                                    (world02_2d.x, world02_2d.y, 0, 0),
                                    (0, 0, world02_2d.x, world02_2d.y)))
            try:
                mCoeffs = solve(world2DMatrix, texCoordsVec)
            except:
                return texstring + dummy
            right_2dworld = Vector(mCoeffs[0:2])
            up_2dworld = Vector(mCoeffs[2:4])

            # These are the final scale values
            # (avoid division by 0 for degenerate or missing UVs)
            scalex = 1 / max(0.00001, right_2dworld.length)
            scaley = 1 / max(0.00001, up_2dworld.length)
            scale = Vector((scalex, scaley))

            # Get the angles of the texture axes. These are in the 2d world
            # coordinate system, so they're relative to the 01 vector
            right_2dworld_angle = math.atan2(right_2dworld.y, right_2dworld.x)
            up_2dworld_angle = math.atan2(up_2dworld.y, up_2dworld.x)

            # Recreate the texture axes in 3d world coordinates,
            # using the angles from the 01 edge
            rt = world01.normalized()
            up = rt.copy()
            rt.rotate(Matrix.Rotation(right_2dworld_angle, 3, face.normal))
            up.rotate(Matrix.Rotation(up_2dworld_angle, 3, face.normal))

            # Now we just need the offsets
            rt_full = rt.to_4d()
            up_full = up.to_4d()
            test_s = V[0].dot(rt) / (width * scale.x)
            test_t = V[0].dot(up) / (height * scale.y)
            rt_full[3] = (T[0].x - test_s) * width
            up_full[3] = (T[0].y - test_t) * height

            texstring += f" [ {self.printvec(rt_full)} ]"\
                        f" [ {self.printvec(up_full)} ]"\
                        f" 0 {self.printvec(scale)}"

        elif self.option_uv == 'Quake':
            # offsetU offsetV rotation scaleU scaleV
            dummy = ' 0 0 0 1 1'

            # 01 and 02 in 3D space
            world01 = V[1] - V[0]
            world02 = V[2] - V[0]

            # 01 and 02 projected along the closest axis
            maxn = max( abs(round(co,self.option_fp)) for co in face.normal )
            for i in [2,0,1]: # axis priority for 45 degree angles
                if round(abs(face.normal[i]),self.option_fp) == maxn:
                    axis = i
                    break
            world01_2d = Vector((world01[:axis] + world01[(axis+1):]))
            world02_2d = Vector((world02[:axis] + world02[(axis+1):]))

            # 01 and 02 in UV space (scaled to texture size)
            tex01 = T[1] - T[0]
            tex02 = T[2] - T[0]
            tex01.x *= width
            tex02.x *= width
            tex01.y *= height
            tex02.y *= height

            # Find affine transformation between 2D and UV
            texCoordsVec = Vector((tex01.x, tex01.y, tex02.x, tex02.y))
            world2DMatrix = Matrix(((world01_2d.x, world01_2d.y, 0, 0),
                                    (0, 0, world01_2d.x, world01_2d.y),
                                    (world02_2d.x, world02_2d.y, 0, 0),
                                    (0, 0, world02_2d.x, world02_2d.y)))
            try:
                mCoeffs = solve(world2DMatrix, texCoordsVec)
            except:
                return texstring + dummy

            # Build the transformation matrix and decompose it
            tformMtx = Matrix(( (mCoeffs[0], mCoeffs[1], 0),
                                (mCoeffs[2], mCoeffs[3], 0),
                                (0,          0,          1) ))
            rotation = math.degrees(tformMtx.inverted_safe().to_euler().z)
            scale = tformMtx.inverted_safe().to_scale() # never zero
            scale.x *= math.copysign(1,tformMtx.determinant())

            # Calculate offsets
            t0 = Vector((T[0].x * width, T[0].y * height))
            v0 = Vector((V[0][:axis] + V[0][(axis+1):]))
            v0.rotate(Matrix.Rotation(math.radians(-rotation), 2))
            v0 = Vector((v0.x/scale.x, v0.y/scale.y))
            offset = t0 - v0
            offset.y *= -1 # v is flipped

            finvals = [offset.x, offset.y, rotation, scale.x, scale.y]
            texstring += f" {self.printvec(finvals)}"

        elif self.option_uv == 'BPrim':
            # ( ( a1 a2 a3 ) ( a4 a5 a6 ) )
            dummy = '( ( 0.0078125 0 0 ) ( 0 0.0078125 0 ) ) '
            '''
            Brush Primitives format

            t = A * B * v, where:
            t is the vertex in UV
            v is the same vertex in 3D
            B transforms world space so that X axis points along face normal
            A is a homogenous matrix that transforms this new space to UV

            B has to match the one arbitrarily chosen in editor and compiler
            A has first two rows stored in map file and third row as (0 0 1)

            t[i] = A * (B * v[i]) = A * vb[i]

            for every vertex:
            [ u ]   [ a1 a2 a3 ] [ xb ]
            [ v ] = [ a4 a5 a6 ] [ yb ]
            [ 1 ]   [ 0  0  1  ] [ zb ]

            1 = zb
            u = a1*xb + a2*yb + a3
            v = a4*xb + a5*yb + a6

            three verts, six unknowns, six equations
            [ u1 ]   [ x1b y1b 1   0   0   0 ] [ a1 ]
            [ v1 ] = [ 0   0   0   x1b y1b 1 ] [ a2 ]
            [ u2 ]   [ x2b y2b 1   0   0   0 ] [ a3 ]
            [ v2 ] = [ 0   0   0   x2b y2b 1 ] [ a4 ]
            [ u3 ]   [ x3b y3b 1   0   0   0 ] [ a5 ]
            [ v3 ] = [ 0   0   0   x3b y3b 1 ] [ a6 ]
            '''
            n = face.normal
            # angle between the X axis and normal's projection onto XY plane
            theta_z = math.atan2(n.y, n.x) if (1-abs(n.z) > 1e-7) else 0
            # angle between the normal and its projection onto XY plane
            theta_y = math.atan2(n.z, math.sqrt(n.x**2 + n.y**2))

            # Brush Primitives specific matrix B, spins world around Z and Y
            b11 = -math.sin(theta_z)
            b12 = math.cos(theta_z)
            b21 = math.sin(theta_y) * math.cos(theta_z)
            b22 = math.sin(theta_y) * math.sin(theta_z)
            b23 = -math.cos(theta_y)
            B = Matrix(( (b11, b12, 0  ),
                         (b21, b22, b23),
                         (0,   0,   0  ) ))
            VB = [B @ vert for vert in V]

            # v is flipped
            T6 = [ T[0].x, -T[0].y, T[1].x, -T[1].y, T[2].x, -T[2].y ]

            M6 = [[VB[0].x, VB[0].y, 1,       0,       0,       0],
                  [0,       0,       0,       VB[0].x, VB[0].y, 1],
                  [VB[1].x, VB[1].y, 1,       0,       0,       0],
                  [0,       0,       0,       VB[1].x, VB[1].y, 1],
                  [VB[2].x, VB[2].y, 1,       0,       0,       0],
                  [0,       0,       0,       VB[2].x, VB[2].y, 1]]
            try:
                A6 = solve(M6, T6)
            except:
                return dummy + texstring
            # unlike other formats, coordinates go before the material name
            texstring = f"( ( {self.printvec(A6[0:3])} )"\
                        f"  ( {self.printvec(A6[3:6])} ) ) " + texstring
        return texstring


    def process_object(self, obj, fw, template):
        flags = self.faceflags(obj)
        origin = self.gridsnap(obj.matrix_world.translation)
        obj.data.materials.append(None) # empty slot for new faces
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        if self.option_tm:
            bmesh.ops.transform(bm, matrix=obj.matrix_world,
                                            verts=bm.verts)
        for vert in bm.verts:
            vert.co = self.gridsnap(vert.co)

        if self.option_geo == 'Brush':
            hull = bmesh.ops.convex_hull(bm, input=bm.verts)
            interior = [face for face in bm.faces if face not in hull['geom']]
            bmesh.ops.delete(bm, geom=interior, context='FACES')
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            bmesh.ops.join_triangles(bm, faces=bm.faces,
                angle_face_threshold=0.01, angle_shape_threshold=0.7)
            bmesh.ops.connect_verts_nonplanar(bm, faces=bm.faces,
                                                angle_limit=0.0)
            fw(template[0])
            for face in bm.faces:
                fw(self.brushplane(face))
                fw(self.texdata(face, bm, obj) + flags)
            fw(template[1])

        else: # export individual faces
            bmesh.ops.connect_verts_concave(bm, faces=bm.faces) # concave poly
            if self.option_tj:
                tjfaces = []
                for face in bm.faces:
                    for loop in face.loops:
                        if abs(loop.calc_angle() - math.pi) <= 1e-4:
                            tjfaces.append(face)
                            break
                bmesh.ops.triangulate(bm, faces=tjfaces) # mid-edge verts
            bmesh.ops.connect_verts_nonplanar(bm, faces=bm.faces,
                                            angle_limit=1e-3) # concave surface
            if self.option_geo == 'Soup':
                bottom = min(vert.co.z for vert in bm.verts)
                bottom = self.gridsnap(bottom - self.option_depth)

            for face in bm.faces[:]:
                if face.calc_area() <= 1e-4:
                    continue
                fw(template[0])
                fw(self.brushplane(face))
                fw(self.texdata(face, bm, obj) + flags) # write original face
                
                if self.option_geo in ('Faces', 'Blob'):
                    new = bmesh.ops.poke(bm, faces=[face],
                                offset=-self.option_depth)
                    if self.option_geo == 'Blob':
                        new['verts'][0].co = origin
                    else:
                        new['verts'][0].co = self.gridsnap(new['verts'][0].co)
                elif self.option_geo in ('Prisms', 'Soup'):
                    fnormal = face.normal
                    new = bmesh.ops.extrude_discrete_faces(bm, faces=[face])
                    if self.option_geo == 'Prisms':
                        bmesh.ops.translate(bm, vec=fnormal*-self.option_depth,
                                                verts=new['faces'][0].verts)
                    elif self.option_geo == 'Soup':
                        for vert in new['faces'][0].verts:
                            vert.co.z = bottom
                    geom = bmesh.ops.region_extend(bm, use_faces=True,
                                                    geom=new['faces'])
                    new['faces'].extend(geom['geom'])
                    
                for newface in new['faces']: # write new faces
                    newface.normal_flip()
                    newface.material_index = len(obj.data.materials) - 1
                    fw(self.brushplane(newface))
                    fw(self.texdata(newface, bm, obj) + flags)
                fw(template[1])

        bm.free()
        obj.data.materials.pop() # remove the empty slot


    def execute(self, context):
        timer = time.time()
        geo = []
        fw = geo.append
        wspwn_objs, bmodel_objs = [],[]

        if self.option_brush == 'Doom3':
            fw('Version 2\n')
            template = ['{\nbrushDef3\n{\n', '}\n}\n']
        elif self.option_uv == 'BPrim':
            template = ['{\nbrushDef\n{\n', '}\n}\n']
        else:
            template = ['{\n', '}\n']
        fw('{\n"classname" "worldspawn"\n')
        if self.option_uv == 'Valve':
            fw('"mapversion" "220"\n')

        if self.option_sel:
            objects = context.selected_objects
        else:
            objects = context.scene.objects
        for obj in objects:
            if obj.type != 'MESH':
                continue
            if ((self.option_group == 'None')
                or (self.option_group == 'Auto' and self.option_geo == 'Brush'
                    and obj.users_collection[0].name.startswith('worldspawn'))
                or (self.option_group == 'Auto' and self.option_geo != 'Brush'
                    and obj.name.startswith('worldspawn'))):
                        wspwn_objs.append(obj)
            else:
                bmodel_objs.append(obj)

        for obj in wspwn_objs:
            self.process_object(obj, fw, template)
        collections = [bpy.context.scene.collection] + bpy.data.collections[:]
        for col in collections:
            if col.objects:
                if self.option_geo == 'Brush':
                    fw(self.entname(col))
                for obj in col.objects:
                    if obj in bmodel_objs:
                        if self.option_geo != 'Brush':
                            fw(self.entname(obj))
                        self.process_object(obj, fw, template)
        fw('}\n')

        if self.option_dest == 'File':
            with open(self.filepath, 'w') as file:
                file.write(''.join(geo))
        else:
            bpy.context.window_manager.clipboard = ''.join(geo)

        timer = time.time() - timer
        self.report({'INFO'},f"Finished exporting map, took {timer:g} sec")
        return {'FINISHED'}

def menu_func_export(self, context):
    self.layout.operator(ExportQuakeMap.bl_idname, text="Quake Map (.map)")

def register():
    bpy.utils.register_class(ExportQuakeMap)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

def unregister():
    bpy.utils.unregister_class(ExportQuakeMap)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
