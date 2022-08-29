# Blender MAP Exporter

This addon allows exporting Blender scenes to Quake .map file format.

Supported Blender versions: 2.83 - 3.2.2+  
Supported game formats: Quake, Half-Life, Quake 2, Quake 3, Doom 3, Quake 4  
Other Quake-derived games (Jedi Academy, Call of Duty, etc) are untested, but hopefully also compatible.

Meshes will be exported to brushes (either as individual faces, or as convex hulls of each mesh). Curves and metaballs are treated as meshes. NURBS surfaces can either be exported as patches, or be converted to meshes on export. The addon will also export lights, cameras, and empty objects as point entities, with any custom properties they may have.

The addon offers UVs in "Standard Quake", "Valve220" and "Brush Primitives" formats, custom grid and precision, automatic triangulation of concave surfaces, detail flag assignment, export to clipboard in plaintext and GTK formats, geometry scaling with adaptive light intensity, and automatic spotlight creation.


## Installation
Download [io_export_qmap.py](https://github.com/c-d-a/io_export_qmap/raw/master/io_export_qmap.py), then select it under "Edit > Preferences > Add-ons > Install".  
Older Blender versions may show an error about missing preferences on first setup - try enabling the addon again.  
The addon preferences allow you to change the default settings used in the export dialogue. They only take effect after restarting Blender.
![pref](https://user-images.githubusercontent.com/55441216/187100568-f4f689ff-39c8-4cf4-b166-146cfc9a1b79.png)


## Mesh Options
The map format requires each brush to be convex.  
There are many ways to represent a mesh with brushes, each with their pros and cons.
![001-015](https://user-images.githubusercontent.com/55441216/187100469-4b5e427d-c0ab-420b-aa68-8abb5e55ddb0.gif)


## Formats
In most cases .map file is an intermediary between the editor and the compiler. So in practice, the output format can be anything, as long as it's supported by the other tools. For example, Quake 1 tools have broad support for Valve220 UV format, but only very limited support for patches.

### Planes
Brushes are defined by planes, rather than by individual vertices. This is an important distinction to keep in mind, because when exporting detailed geometry, you will need enough precision to represent each plane. Otherwise, any face with more than three verts may end up leaving gaps. Soft maximum of 17 decimal places roughly matches TrenchBroom's precision.  
Most games use the original Quake format, defining planes by three verts. Doom 3 introduced a new format, using a plane equation.

### UVs
Since the .map format doesn't store individual vertices, it doesn't store individual verts' UVs either. Instead, it defines texture coordinates per plane. The exporter uses two arbitrarily selected edges for this task. In practice, this means that it is impossible to maintain perspective warp, unless you triangulate every face in advance.

Texture coordinates in the legacy "Standard Quake" format have the broadest support, but also potentially lose a lot of information, as shearing is unsupported (only rotation and scale along world axes). The two other formats, "Valve220" and "Brush Primitives", are more advanced and have similar capabilities to each other. So the choice only depends on whether your editor and compiler support them.

### Flags
Quake 2 introduced flags for defining various special properties (lights, etc). The flags carried over to Quake 3, still remained in vestigial form in Doom 3, and were removed in the Quake 4 format.  
The exporter currently only supports the Detail flag. For any face belonging to an object or to a collection with "detail" anywhere in their name, the exported surface will get its Detail flag set.

### Clipboard
For convenience, the exporter can put the map data into the system clipboard, instead of writing it to a .map file. In this case, the filename in the export dialogue is ignored, and the data is ready to be pasted directly into an open map in your editor of choice. Some functionality may depend on the editor automatically re-assigning the entity names and targets.

Supported formats: text clipboard (TrenchBroom), GTK clipboard (GTKRadiant, NetRadiant, etc).  
GTK clipboard is currently Windows-only. DarkRadiant clipboard is not supported.
