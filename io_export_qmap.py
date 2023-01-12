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
    "version": (2023, 1, 12),
    "blender": (3, 4, 1),
    "location": "File > Import-Export",
    "description": "Export scene to idTech map format",
    "category": "Import-Export",
    "doc_url": "https://github.com/c-d-a/io_export_qmap"
}

import bpy, bmesh, math, time
from mathutils import Vector, Matrix, Euler, geometry
from numpy.linalg import solve
from numpy import format_float_positional as fformat
from bpy_extras.io_utils import ExportHelper
from bpy.props import *

# clipboard stuff
import sys, struct, ctypes
if sys.platform.startswith("win"):
    from ctypes import wintypes as w32
    k32 = ctypes.windll.kernel32
    u32 = ctypes.windll.user32
    k32.GlobalAlloc.argtypes = w32.UINT, ctypes.c_size_t
    k32.GlobalAlloc.restype = w32.HGLOBAL
    k32.GlobalLock.argtypes = w32.HGLOBAL,
    k32.GlobalLock.restype = w32.LPVOID
    k32.GlobalUnlock.argtypes = w32.HGLOBAL,
    k32.RtlCopyMemory.argtypes = w32.LPVOID, w32.LPCVOID, ctypes.c_size_t
    u32.OpenClipboard.argtypes = w32.HWND,
    u32.SetClipboardData.argtypes = w32.UINT, w32.HANDLE

ptxt = {
    'sel': {'name':"Selection only", 'def':True,
        'desc':"Only export selected objects"},
    'tm':  {"name":"Apply transform", "def":True,
        "desc":"Apply current rotation, translation and scale"},
    'mod': {"name":"Apply modifiers", "def":True,
        "desc":"Apply modifiers before export, using their viewport settings"},
    'tj': {"name":"Triangulate 180°", "def":True,
        "desc":"Split faces with mid-edge vertices (for better UVs)"},

    'geo': {"name":"Mesh", "def":'Faces',
        "items":(
            ('Brush',"Brush","Export each mesh as a single brush"\
                "\n\nMore control, but takes more effort to prepare"\
                "\nBy default, brushes are grouped by collection"),
            ('Faces',"Faces","Export each face as a pyramid brush"\
                "\n\nBest for detailed geometry, but hard to edit later"),
            ('Prisms',"Walls","Export each face as an extruded prism brush"\
                "\n\nBest for simple walls that you plan to edit afterwards"),
            ('Soup',"Terrain","Export faces as vertically extruded poly soup"\
                "\n\nExtrudes faces along Z to their lowest vert's height"\
                "\nUseful when you want to save on collision planes"),
            ('Blob',"Blob","Export faces as pyramids with a common apex"\
                "\n\nPuts the shared apex at object's origin point"\
                "\nUseful when you want a solid sealed convex-ish asteroid"),
            ('Miter',"Shell","Export faces as a solidified shell"\
                "\n\nExtrudes along vert normals, with miter joints inbetween"\
                "\nUnreliable, as the resulting joints may be non-planar") )},
    'nurbs': {"name":"Nurbs", "def":'Mesh',
        "items":(
            ('None', "Ignore", "Ignore NURBS surfaces"),
            ('Mesh', "Mesh", "Convert NURBS to meshes, export as brushes"),
            ('Def2', "Dynamic", "Export NURBS as patchDef2 patches"\
                " (dynamic subdivision)\n\nFor a better preview in Blender:"\
                "\nEnable Bezier, Endpoints, and set Order to 3x3"\
                "\nSelect all points and set their W to 100 or higher"),
            ('Def3', "Fixed", "Export NURBS as patchDef3 patches"\
                " (explicit subdivision)\n\nFor a better preview in Blender:"\
                "\nEnable Bezier, Endpoints, and set Order to 3x3"\
                "\nSelect all points and set their W to 100 or higher") )},
    'lights': {"name":"Light", "def":'Auto',
        "items":(
            ('None', "Ignore", "Ignore light objects"),
            ('Auto', "Adaptive", "Export lights, approximate intensity"\
                "\n\nAttempts to match the lights' appearance"\
                " by scaling their brightness with the scene scale."\
                "\nNote that for exporting in 1:1 scale, light intensity"\
                " will likely need to be in the thousands."\
                "\n\nSpotlights automatically get a target."\
                "\nidTech4-format lights can be exported by choosing"\
                " 'Doom 3' as the brush plane format"),
            ('AsIs', "Explicit", "Export lights, use intensity as is"\
                "\n\nSame as 'Adaptive', except intensity will be used as is."\
                "\nMostly useful with imported maps and pre-set lights") )},
    'empties': {"name":"Empty", "def":'Point',
        "items":(
            ('None', "Ignore", "Ignore empty objects"),
            ('Point', "Entities", "Export empties as point entities"\
                "\n\nUses object name as 'classname', rotation as 'angles'"\
                " and custom object properties as key/value pairs"\
                "\nThis also exports cameras, maintaining their direction") )},

    'grid': {"name":"Grid", "def":1.0,
        "desc":"Grid size to snap coordinates to\n(0 = don't snap)"},
    'depth': {"name":"Depth", "def":2.0,
        "desc":"Offset for extrusion, pyramid apex and terrain bottom"\
            "\n\nWhen using a larger grid, make sure to increase this as well"},
    'scale': {"name":"Scale", "def":1.0,
        "desc":"Scale factor for all 3D coordinates"\
        "\n\n1 Quake unit is approximately 1 inch"\
        "\nA scale of about 40-48 is appropriate for a scene in meters"},
    'fp': {"name":"Precision", "def":5,
        "desc":"Number of decimal places"},

    'brush': {"name":"Planes", "def":'Quake',
        "items":(
            ('Quake', "Quake", "Brush planes as three vertices"\
                "\n(Quake, Half-Life, Quake 2, Quake 3)"),
            ('Doom3', "Doom 3", "Brush planes as normal + distance"\
                "\n(Doom 3, Quake 4)") )},
    'uv': {"name":"UVs", "def":'Valve',
        "items":(
            ('Quake', "Standard", "World-aligned texture projection"),
            ('Valve', "Valve", "Edge-bound texture projection"),
            ('BPrim', "Primitives", "Plane-bound texture projection") )},
    'flags': {"name":"Flags", "def":'None',
        "items":(
            ('None', "None", "No flags"\
                "\n(Quake, Half-Life, Quake 4)"),
            ('Q2', "Quake 2", "Content, Surface, Value"\
                "\n(Quake 2, Quake 3, Doom 3)"\
                "\n\nSets the Detail flag for faces that belong to:"\
                "\n - a face map,\n - an object,\n - or a collection"\
                "\nwith 'detail' in their name") )},
    'dest': {"name":"Output", "def":'File',
        "items":(
            ('File', "File", "Save to a .map file"),
            ('Clip', "Text", "Store in text clipboard"\
                "\n\nCan then be pasted in TrenchBroom"),
            ('GTK', "GTK", "Store in GTK clipboard"\
                "\n\nCan then be pasted in GTKRadiant, NetRadiant, etc") )},

    'group': {"name":"Grouping", "def":'Gen',
        "items":(
            ('None', "None", "Export loose worldspawn brushes"),
            ('Auto', "Blender", "Group under object/collection names"\
                "\n\nTrailing numbers after the name will be removed\n"\
                "Use 'worldspawn' name on objects you want to keep ungrouped"),
            ('Gen', "Generic", "Group under generic classnames (set below)"))},
    'gname': {"name":"Generic classname", "def":'func_group',
        "desc":"Class name for brush entities, unless set otherwise"\
            "\n\ne.g.:\nfunc_group\nfunc_detail"},
    'skip': {"name":"Generic material", "def":'skip',
        "desc":"Material to use on new and unassigned faces"\
            "\n\ne.g.:\nskip\ntextures/common/caulk"},
    'size': {"name":"Generic size", "def":'64',
        "items":(('16','16',''),('32','32',''),('64','64',''),('128','128',''),
                ('256','256',''),('512','512',''),('1024','1024','')),
        "desc":"Generic size for UV scaling on materials without texture maps"}
}


class ExportQuakeMapObjectPanel(bpy.types.Panel):
    bl_idname = "OBJECT_PT_QMAP_Props"
    bl_label = "idTech Map Export"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "object"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        self.layout.prop(context.active_object, "qmap_geo_type")


class ExportQuakeMapPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    sel: BoolProperty(name=ptxt['sel']['name'],
        default=ptxt['sel']['def'], description=ptxt['sel']['desc'])
    tm: BoolProperty(name=ptxt['tm']['name'],
        default=ptxt['tm']['def'], description=ptxt['tm']['desc'])
    mod: BoolProperty(name=ptxt['mod']['name'],
        default=ptxt['mod']['def'], description=ptxt['mod']['desc'])
    tj: BoolProperty(name=ptxt['tj']['name'],
        default=ptxt['tj']['def'], description=ptxt['tj']['desc'])
    geo: EnumProperty(name=ptxt['geo']['name'],
        default=ptxt['geo']['def'], items=ptxt['geo']['items'])
    nurbs: EnumProperty(name=ptxt['nurbs']['name'],
        default=ptxt['nurbs']['def'], items=ptxt['nurbs']['items'])
    lights: EnumProperty(name=ptxt['lights']['name'],
        default=ptxt['lights']['def'], items=ptxt['lights']['items'])
    empties: EnumProperty(name=ptxt['empties']['name'],
        default=ptxt['empties']['def'], items=ptxt['empties']['items'])
    grid: FloatProperty(name=ptxt['grid']['name'], min=0,
        default=ptxt['grid']['def'], description=ptxt['grid']['desc'])
    depth: FloatProperty(name=ptxt['depth']['name'],
        default=ptxt['depth']['def'], description=ptxt['depth']['desc'])
    scale: FloatProperty(name=ptxt['scale']['name'],
        default=ptxt['scale']['def'], description=ptxt['scale']['desc'])
    fp: IntProperty(name=ptxt['fp']['name'], min=0, soft_max=17,
        default=ptxt['fp']['def'], description=ptxt['fp']['desc'])
    brush: EnumProperty(name=ptxt['brush']['name'],
        default=ptxt['brush']['def'], items=ptxt['brush']['items'])
    uv: EnumProperty(name=ptxt['uv']['name'],
        default=ptxt['uv']['def'], items=ptxt['uv']['items'])
    flags: EnumProperty(name=ptxt['flags']['name'],
        default=ptxt['flags']['def'], items=ptxt['flags']['items'])
    dest: EnumProperty(name=ptxt['dest']['name'],
        default=ptxt['dest']['def'], items=ptxt['dest']['items'])
    group: EnumProperty(name=ptxt['group']['name'],
        default=ptxt['group']['def'], items=ptxt['group']['items'])
    gname: StringProperty(name=ptxt['gname']['name'],
        default=ptxt['gname']['def'], description=ptxt['gname']['desc'])
    skip: StringProperty(name=ptxt['skip']['name'],
        default=ptxt['skip']['def'], description=ptxt['skip']['desc'])
    size: EnumProperty(name=ptxt['size']['name'], items=ptxt['size']['items'],
        default=ptxt['size']['def'], description=ptxt['size']['desc'])

    def draw(self, context):
        self.layout.label(text="Default export settings", icon='PREFERENCES')
        spl = self.layout.row().split(factor=0.22)
        col = spl.column()
        for p in ["grid", "depth", "scale", "fp"]: col.prop(self, p)
        spl = spl.split(factor=0.33)
        col = spl.column()
        for p in ["geo", "nurbs", "lights", "empties"]: col.prop(self, p)
        spl = spl.split(factor=0.5)
        col = spl.column()
        for p in ["brush", "uv", "flags", "dest"]: col.prop(self, p)
        col = spl.column()
        for p in ["sel", "tm", "mod", "tj"]: col.prop(self, p)
        col = self.layout.column()
        for p in ["group", "gname", "skip", "size"]: col.prop(self, p)

bpy.utils.register_class(ExportQuakeMapPreferences)


class ExportQuakeMap(bpy.types.Operator, ExportHelper):
    bl_idname = 'export.map'
    bl_label = bl_info['name']
    bl_description = bl_info['description']
    bl_options = {'UNDO', 'PRESET'}
    filename_ext = ".map"
    filter_glob: StringProperty(default="*.map", options={'HIDDEN'})
    prefs = bpy.context.preferences.addons[__name__].preferences

    option_sel: BoolProperty(name=ptxt['sel']['name'],
        default=prefs.sel, description=ptxt['sel']['desc'])
    option_tm: BoolProperty(name=ptxt['tm']['name'],
        default=prefs.tm, description=ptxt['tm']['desc'])
    option_mod: BoolProperty(name=ptxt['mod']['name'],
        default=prefs.mod, description=ptxt['mod']['desc'])
    option_tj: BoolProperty(name=ptxt['tj']['name'],
        default=prefs.tj, description=ptxt['tj']['desc'])
    option_geo: EnumProperty(name=ptxt['geo']['name'],
        default=prefs.geo, items=ptxt['geo']['items'])
    option_nurbs: EnumProperty(name=ptxt['nurbs']['name'],
        default=prefs.nurbs, items=ptxt['nurbs']['items'])
    option_lights: EnumProperty(name=ptxt['lights']['name'],
        default=prefs.lights, items=ptxt['lights']['items'])
    option_empties: EnumProperty(name=ptxt['empties']['name'],
        default=prefs.empties, items=ptxt['empties']['items'])
    option_grid: FloatProperty(name=ptxt['grid']['name'], min=0,
        default=prefs.grid, description=ptxt['grid']['desc'])
    option_depth: FloatProperty(name=ptxt['depth']['name'],
        default=prefs.depth, description=ptxt['depth']['desc'])
    option_scale: FloatProperty(name=ptxt['scale']['name'],
        default=prefs.scale, description=ptxt['scale']['desc'])
    option_fp: IntProperty(name=ptxt['fp']['name'], min=0, soft_max=17,
        default=prefs.fp, description=ptxt['fp']['desc'])
    option_brush: EnumProperty(name=ptxt['brush']['name'],
        default=prefs.brush, items=ptxt['brush']['items'])
    option_uv: EnumProperty(name=ptxt['uv']['name'],
        default=prefs.uv, items=ptxt['uv']['items'])
    option_flags: EnumProperty(name=ptxt['flags']['name'],
        default=prefs.flags, items=ptxt['flags']['items'])
    option_dest: EnumProperty(name=ptxt['dest']['name'],
        default=prefs.dest, items=ptxt['dest']['items'])
    option_group: EnumProperty(name=ptxt['group']['name'],
        default=prefs.group, items=ptxt['group']['items'])
    option_gname: StringProperty(name=ptxt['gname']['name'],
        default=prefs.gname, description=ptxt['gname']['desc'])
    option_skip: StringProperty(name=ptxt['skip']['name'],
        default=prefs.skip, description=ptxt['skip']['desc'])
    option_size: EnumProperty(name=ptxt['size']['name'], default=prefs.size,
        items=ptxt['size']['items'], description=ptxt['size']['desc'])

    # all encountered names, including duplicates
    seen_names = []
    # offset spotlight targets by 64 units, regardless of chosen scale
    spot_name, spot_class, spot_offset = "spot_target_", "info_null", 64
    # export cameras as point entities, match entity's +X to camera's -Z
    cam_correct = Euler((-math.pi/2, 0, math.pi/2),'ZXY').to_matrix().to_4x4()


    def draw(self, context):
        o = "option_"
        self.layout.separator()
        spl = self.layout.row().split(factor=0.5)
        col = spl.column()
        for p in [o+"sel",o+"tm"]: col.prop(self, p)
        col = spl.column()
        for p in [o+"mod",o+"tj"]: col.prop(self, p)
        self.layout.separator()
        self.layout.label(text="Object types", icon='SCENE_DATA')
        spl = self.layout.row().split(factor=0.5)
        col = spl.column()
        for p in [o+"geo",o+"nurbs"]: col.prop(self, p)
        col = spl.column()
        for p in [o+"lights",o+"empties"]: col.prop(self, p)
        self.layout.separator()
        self.layout.label(text="Coordinates", icon='MESH_DATA')
        spl = self.layout.row().split(factor=0.5)
        col = spl.column()
        for p in [o+"grid",o+"depth"]: col.prop(self, p)
        col = spl.column()
        for p in [o+"scale",o+"fp"]: col.prop(self, p)
        self.layout.separator()
        self.layout.label(text="Output format", icon='UV_DATA')
        spl = self.layout.row().split(factor=0.5)
        col = spl.column()
        for p in [o+"brush",o+"uv"]: col.prop(self, p)
        col = spl.column()
        for p in [o+"flags",o+"dest"]: col.prop(self, p)
        self.layout.separator()
        self.layout.label(text="Miscellaneous", icon='GROUP')
        col = self.layout.column()
        col.prop(self, o+"group")
        col.prop(self, o+"gname", text="Class")
        col.prop(self, o+"skip", text="Material")
        col.prop(self, o+"size", text="Tex size")


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
        fstring = []
        for co in vector:
            fstring.append(fformat(co, precision=self.option_fp, trim='-'))
        return ' '.join(fstring)


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


    def faceflags(self, face, mesh, obj):
        if self.option_flags == 'None':
            return "\n"
        elif self.option_flags == 'Q2':
            col = obj.users_collection[0]
            if len(obj.face_maps) > 0:
                obj.face_maps.new() # faces w/o face maps have index -1 (?)
                fm_layer = mesh.faces.layers.face_map.verify()
                fm_name = obj.face_maps[face[fm_layer]].name
                obj.face_maps.remove(obj.face_maps[-1])
            else:
                fm_name = ''
            names = obj.name + col.name + fm_name
            if 'detail' in names.lower():
                return f" {1<<27} 0 0\n"
            else:
                return " 0 0 0\n"


    def texdata(self, face, mesh, obj):
        mat = None
        width = height = int(self.option_size)
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


    def process_mesh(self, obj, fw, template):
        geo_type = obj.qmap_geo_type
        if geo_type == 'Default':
            geo_type = self.option_geo
        origin = self.gridsnap(obj.matrix_world.translation)
        obj.data.materials.append(None) # empty slot for new faces
        orig_obj = obj
        if self.option_mod or obj.type != 'MESH':
            obj = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        bm = bmesh.new()
        bm.from_mesh(obj.to_mesh())
        if self.option_tm:
            bmesh.ops.transform(bm, matrix=obj.matrix_world,
                                            verts=bm.verts)
        for vert in bm.verts:
            vert.co = self.gridsnap(vert.co * self.option_scale)

        if geo_type == 'Brush':
            hull = bmesh.ops.convex_hull(bm, input=bm.verts,
                                        use_existing_faces=True)
            geom_hull = hull['geom'] + hull['geom_holes']
            interior = [face for face in bm.faces if face not in geom_hull]
            bmesh.ops.delete(bm, geom=interior, context='FACES')
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            bmesh.ops.join_triangles(bm, faces=bm.faces,
                angle_face_threshold=0.01, angle_shape_threshold=0.7)
            bmesh.ops.connect_verts_nonplanar(bm, faces=bm.faces,
                                                angle_limit=0.0)
            fw(template[0])
            for face in bm.faces:
                flags = self.faceflags(face, bm, orig_obj)
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
            if geo_type == 'Soup':
                bottom = min(vert.co.z for vert in bm.verts)
                bottom -= self.option_depth

            for face in bm.faces[:]:
                if face.calc_area() <= 1e-4:
                    continue
                flags = self.faceflags(face, bm, orig_obj)
                fw(template[0])
                fw(self.brushplane(face))
                fw(self.texdata(face, bm, obj) + flags) # write original face

                if geo_type in ('Faces', 'Blob'):
                    new = bmesh.ops.poke(bm, faces=[face],
                                offset=-self.option_depth)
                    if geo_type == 'Blob':
                        new['verts'][0].co = origin
                    elif geo_type == 'Faces':
                        new['verts'][0].co = self.gridsnap(new['verts'][0].co)

                elif geo_type in ('Prisms', 'Soup', 'Miter'):
                    clone = face.copy() # keep original face & vertex normals
                    new = bmesh.ops.extrude_discrete_faces(bm, faces=[clone])
                    new_verts = new['faces'][0].verts

                    if geo_type == 'Prisms':
                        bmesh.ops.translate(bm, verts=new_verts,
                            vec=face.normal * -self.option_depth)
                    elif geo_type == 'Soup':
                        for vert in new_verts:
                            vert.co.z = bottom
                    elif geo_type == 'Miter':
                        for new_v, orig_v in zip(new_verts, face.verts):
                            new_v.co -= (orig_v.normal *
                                orig_v.calc_shell_factor() * self.option_depth)

                    geom = bmesh.ops.region_extend(bm, use_faces=True,
                                                    geom=new['faces'])
                    new['faces'].extend(geom['geom'])

                bm.normal_update()
                for newface in new['faces']: # write new faces
                    newface.normal_flip()
                    newface.material_index = len(obj.data.materials) - 1
                    fw(self.brushplane(newface))
                    fw(self.texdata(newface, bm, obj) + flags)
                fw(template[1])

        bm.free()
        orig_obj.data.materials.pop() # remove the empty slot


    def process_patch(self, obj, spline, fw):
        mat = None
        if obj.material_slots:
            mat = obj.material_slots[spline.material_index].material
        if mat:
            matname = mat.name.replace(" ","_")
        else:
            matname = self.option_skip
        if self.option_brush == 'Doom3':
            matname = f'"{matname}"'

        wu, wv = spline.point_count_u, spline.point_count_v
        nu, nv = wu + spline.use_cyclic_u, wv + spline.use_cyclic_v
        ru, rv = spline.resolution_u + 1, spline.resolution_v + 1
        du, dv = 1/(nu-1), -1/(nv-1) # UV increments (v is flipped)
        if nu%2 == 0 or nv%2 == 0 or nu == 1 or nv == 1:
            self.report({'WARNING'},f"Skipped invalid patch {obj.name}")
            return

        fw('{\npatch'+self.option_nurbs+'\n{\n')
        fw(matname + '\n')
        if self.option_nurbs == 'Def2':
            fw(f"( {nu} {nv} 0 0 0 )\n(\n")
        else:
            fw(f"( {nu} {nv} {ru} {rv} 0 0 0 )\n(\n")
        for i in range(nu):
            fw("( ")
            for j in reversed(range(nv)):
                texuv = (i*du, j*dv)
                index = (j%wv)*wu + (i%wu)
                xyz = spline.points[index].co[:3]
                if self.option_tm:
                    xyz = obj.matrix_world @ Vector(xyz)
                xyz = self.gridsnap(xyz * self.option_scale)
                fw(f"( {self.printvec(xyz)} {self.printvec(texuv)} ) ")
            fw(")\n")
        fw(")\n}\n}\n")


    def process_light(self, obj, fw):
        intensity = obj.data.energy
        origin = obj.matrix_world.to_translation() * self.option_scale
        fw('{\n"classname" "light"\n')
        fw(f'"origin" "{self.printvec(origin)}"\n')
        fw(f'"_color" "{self.printvec(obj.data.color)}"\n')
        if self.option_lights == 'Auto':
            intensity *= self.option_scale**2 / 40**2 # 1 inch = 1 unit
        fw(f'"light" "{intensity}"\n')

        keys = obj.keys()
        if 'delay' not in keys:
            fw(f'"delay" "2"\n') # Q1 attenuation
        pt_size = obj.data.shadow_soft_size
        if '_deviance' not in keys and pt_size != 0.25 :
            fw(f'"_deviance" "{pt_size * self.option_scale}"\n') # Q1,Q3
        for prop in keys: # custom object properties
            if prop not in ('classname','origin','light','_color',
                            'angle','_softangle','radius','target'):
                if isinstance(obj[prop], (int, float, str)): # no arrays
                    fw(f'"{prop}" "{obj[prop]}"\n')

        if obj.data.type == 'POINT':
            if self.option_brush == 'Doom3':
                pt_range = intensity * 10 # eyeballed
                if 'light_radius' not in keys:
                    fw(f'"light_radius" "{pt_range} {pt_range} {pt_range}"\n')
                if 'texture' not in keys:
                    fw(f'"texture" "lights/falloff_exp1"\n')
        elif obj.data.type == 'SPOT':
            spot_ang = obj.data.spot_size
            if self.option_brush == 'Doom3':
                spot_hyp = 10 * self.option_scale
                spot_scale = obj.matrix_world.to_scale()
                spot_fw = math.cos(spot_ang/2) * spot_hyp * spot_scale.z
                spot_rt = math.sin(spot_ang/2) * spot_hyp * spot_scale.x
                spot_up = math.sin(spot_ang/2) * spot_hyp * spot_scale.y
                fw(f'"light_target" "0 0 -{spot_fw}"\n')
                fw(f'"light_right" "{spot_rt} 0 0"\n')
                fw(f'"light_up" "0 {spot_up} 0"\n')
                if 'texture' not in keys:
                    fw(f'"texture" "lights/spot01"\n')
                spot_rot = obj.matrix_world.to_euler().to_matrix()
                d3_rot = [el for row in spot_rot.inverted_safe() for el in row]
                fw(f'"rotation" "{self.printvec(d3_rot)}"\n')
            elif self.option_brush == 'Quake':
                spot_deg = math.degrees(spot_ang)
                spot_inner = spot_deg * (1 - obj.data.spot_blend)
                fw(f'"angle" "{spot_deg}"\n') # Q1
                fw(f'"_softangle" "{spot_inner}"\n') # Q1
                fw(f'"radius" "{math.tan(spot_ang/2) * 64}"\n') # Q3
                self.seen_names.append(self.spot_name)
                spot_num = self.seen_names.count(self.spot_name)
                spot_rot = obj.matrix_world.to_euler().to_matrix()
                spot_org = spot_rot @ Vector((0,0,-self.spot_offset)) + origin
                fw(f'"target" "{self.spot_name}{spot_num}"\n')
                fw('}\n{\n')
                fw(f'"classname" "{self.spot_class}"\n')
                fw(f'"origin" "{self.printvec(spot_org)}"\n')
                fw(f'"targetname" "{self.spot_name}{spot_num}"\n')
        fw('}\n')


    def process_empty(self, obj, fw):
        name = obj.name.rstrip('0123456789')
        name = name[:-1] if name[-1] in ('.',' ') else obj.name
        fw('{\n"classname" "' + name + '"\n')
        origin = obj.matrix_world.to_translation() * self.option_scale
        fw(f'"origin" "{self.printvec(origin)}"\n')
        keys = obj.keys()
        if 'angles' not in keys:
            if obj.type != 'CAMERA':
                ang = obj.matrix_world.to_euler()
            else:
                ang = (obj.matrix_world @ self.cam_correct).to_euler()
            deg = (math.degrees(a) for a in (-ang.y, ang.z, ang.x))
            fw(f'"angles" "{self.printvec(deg)}"\n')
        for prop in keys: # custom object properties
            if isinstance(obj[prop], (int, float, str)): # no arrays
                fw(f'"{prop}" "{obj[prop]}"\n')
        fw('}\n')


    def execute(self, context):
        timer = time.time()
        map_text = []
        fw = map_text.append
        wspwn_objs, bmodel_objs = [],[]
        patch_objs, light_objs, empty_objs = [],[],[]

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

        # sort objects
        if self.option_sel:
            objects = context.selected_objects
        else:
            objects = context.scene.objects
        for obj in objects:
            if obj.type == 'LIGHT' and self.option_lights != 'None':
                light_objs.append(obj)
                continue
            elif obj.type in ('EMPTY','CAMERA'):
                if self.option_empties != 'None':
                    empty_objs.append(obj)
                    continue
            elif obj.type == 'SURFACE':
                if self.option_nurbs in ('Def2','Def3'):
                    patch_objs.append(obj)
                    continue
            elif obj.type == 'META' and '.' in obj.name:
                continue
            elif obj.type not in ('MESH','SURFACE','CURVE','FONT','META'):
                continue

            geo_type = obj.qmap_geo_type
            if geo_type == 'Default':
                geo_type = self.option_geo
            if ((self.option_group == 'None')
                or (self.option_group == 'Auto' and geo_type == 'Brush'
                    and obj.users_collection[0].name.startswith('worldspawn'))
                or (self.option_group == 'Auto' and geo_type != 'Brush'
                    and obj.name.startswith('worldspawn'))):
                        wspwn_objs.append(obj)
            else:
                bmodel_objs.append(obj)

        # process objects
        for obj in wspwn_objs:
            self.process_mesh(obj, fw, template)
        for obj in patch_objs:
            for spline in obj.data.splines:
                self.process_patch(obj, spline, fw)
        collections = [bpy.context.scene.collection] + bpy.data.collections[:]
        for col in collections:
            bmodel_brush_objs, bmodel_face_objs = [],[]
            for obj in [ob for ob in col.objects if ob in bmodel_objs]:
                geo_type = obj.qmap_geo_type
                if geo_type == 'Default':
                    geo_type = self.option_geo
                if geo_type == 'Brush':
                    bmodel_brush_objs.append(obj)
                else:
                    bmodel_face_objs.append(obj)
            if bmodel_brush_objs:
                fw(self.entname(col))
                for obj in bmodel_brush_objs:
                    self.process_mesh(obj, fw, template)
            for obj in bmodel_face_objs:
                fw(self.entname(obj))
                self.process_mesh(obj, fw, template)
        fw('}\n')
        for obj in light_objs:
            self.process_light(obj, fw)
        for obj in empty_objs:
            self.process_empty(obj, fw)

        # handle output
        scene_str = ''.join(map_text)
        if self.option_dest == 'File':
            with open(self.filepath, 'w') as file:
                file.write(scene_str)
        elif self.option_dest == 'Clip':
            bpy.context.window_manager.clipboard = scene_str
        elif self.option_dest == 'GTK':
            gtk_str = struct.pack('<Q',len(scene_str)) + scene_str.encode()
            if sys.platform.startswith("win"):
                clipid = u32.RegisterClipboardFormatW("RadiantClippings")
                handle = k32.GlobalAlloc(0x0042, len(gtk_str))
                pointer = k32.GlobalLock(handle)
                try:
                    k32.RtlCopyMemory(pointer, gtk_str, len(gtk_str))
                    u32.OpenClipboard(u32.GetActiveWindow())
                    u32.EmptyClipboard()
                    u32.SetClipboardData(clipid, handle)
                except:
                    self.report({'ERROR'},"Failed to export GTK clipboard")
                finally:
                    k32.GlobalUnlock(pointer)
                    u32.CloseClipboard()
            else:
                self.report({'ERROR'},"GTK export is currently Windows-only")
                bpy.context.window_manager.clipboard = scene_str

        timer = time.time() - timer
        self.report({'INFO'},f"Finished exporting map, took {timer:g} sec")
        return {'FINISHED'}


def menu_func_export(self, context):
    self.layout.operator(ExportQuakeMap.bl_idname, text="Quake Map (.map)")

def register():
    bpy.utils.register_class(ExportQuakeMap)
    bpy.types.Object.qmap_geo_type = bpy.props.EnumProperty(name="Geo",
        items=(('Default', "Default", "No override"),) + ptxt['geo']['items'],
        description="Mesh export mode override")
    bpy.utils.register_class(ExportQuakeMapObjectPanel)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)

def unregister():
    bpy.utils.unregister_class(ExportQuakeMap)
    bpy.utils.unregister_class(ExportQuakeMapPreferences)
    del bpy.types.Object.qmap_geo_type
    bpy.utils.unregister_class(ExportQuakeMapObjectPanel)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
