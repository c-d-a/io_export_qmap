# Blender MAP Exporter

This addon allows exporting Blender scenes to idTech .map file format.

Supported Blender versions: 2.83 - 3.4+  
Supported game formats: Quake, Half-Life, Quake 2, Quake 3, Doom 3, Quake 4  
Other Quake-derived games (Jedi Academy, Call of Duty, etc) are untested, but hopefully also compatible.

Meshes will be exported to brushes (either as individual faces, or as convex hulls of each mesh). Curves and metaballs are treated as meshes. NURBS surfaces can either be exported as patches, or be converted to meshes on export. The addon will also export lights, cameras, and empty objects as point entities, with any custom properties they may have.

The addon offers UVs in "Standard Quake", "Valve220" and "Brush Primitives" formats, custom grid and precision, automatic triangulation of concave surfaces, detail flag assignment, export to clipboard in plaintext and GTK formats, geometry scaling with adaptive light intensity, and automatic spotlight creation.


## Installation
Download [io_export_qmap.py](https://github.com/c-d-a/io_export_qmap/raw/master/io_export_qmap.py), then select it under "Edit > Preferences > Add-ons > Install".  
Older Blender versions may show an error about missing preferences on first setup - try enabling the addon again.  
The addon preferences allow you to change the default settings used in the export dialogue. They only take effect after restarting Blender.  
![prefs](https://user-images.githubusercontent.com/55441216/211974555-07463f1c-f5a6-4b94-90e4-abfb86a8aba9.png)


## Mesh Options
The map format requires each brush to be convex.  
There are many ways to represent a mesh with brushes, each with their pros and cons.  
(if you can't see the animation below, [open](https://user-images.githubusercontent.com/55441216/187100469-4b5e427d-c0ab-420b-aa68-8abb5e55ddb0.gif) it in another tab or try a different web browser)  
![mesh](https://user-images.githubusercontent.com/55441216/187100469-4b5e427d-c0ab-420b-aa68-8abb5e55ddb0.gif)

For complex scenes, you can override mesh export mode on a per-object basis:  
![override](https://user-images.githubusercontent.com/55441216/211972711-d9cb4629-8ee1-41fa-8a00-831bee7d14ff.png)



## Formats
In most cases .map file is an intermediary between the editor and the compiler. So in practice, the output format can be anything, as long as it's supported by the other tools. For example, Quake 1 tools have broad support for Valve220 UV format, but only very limited support for patches.

### Planes
Brushes are defined by planes, rather than by individual vertices. This is an important distinction to keep in mind, because when exporting detailed geometry, you will need enough precision to represent each plane. Otherwise, any face with more than three verts may end up leaving gaps. Soft maximum of 17 decimal places roughly matches TrenchBroom's precision.  

Most games use the original Quake format, defining planes by three verts. Doom 3 introduced a new format, using a plane equation. While the original format meant that verts of neighboring triangles never drift apart, with Doom 3 planes you get no such guarantee, so you might want to use higher precision even on simple meshes.

### UVs
UV scale depends on texture size. The exporter will use the first texture it finds in the material's node tree, or, failing that, the user-definable fallback size.

Texture coordinates in the legacy "Standard Quake" format have the broadest support, but also potentially lose a lot of information, as it doesn't support shearing (only rotation and scale along world axes). The two other formats, "Valve220" and "Brush Primitives", are more advanced and have similar capabilities to each other. The choice depends on whether your editor and compiler support them.

Since the .map format doesn't store individual vertices, it doesn't store individual verts' UVs either. Instead, it defines texture coordinates per plane. The exporter uses two arbitrarily selected edges for this task. In practice, this means that it is impossible to maintain perspective warp (e.g. on curved pipes), unless you triangulate every face in advance.

### Flags
Quake 2 introduced flags for defining various special properties (lights, etc). The flags carried over to Quake 3, still remained in vestigial form in Doom 3, and were removed in the Quake 4 format.  
The exporter currently only supports the Detail flag. For any face belonging to an object, a collection, or a face map with "detail" anywhere in their name, the exported surface will get its Detail flag set.

### Clipboard
For convenience, the exporter can put the map data into the system clipboard, instead of writing it to a .map file. In this case, the filename in the export dialogue is ignored, and the data is ready to be pasted directly into an open map in your editor of choice. Some functionality may depend on the editor automatically re-assigning the entity names and targets.

Supported formats: text clipboard (TrenchBroom), GTK clipboard (GTKRadiant, NetRadiant, etc).  
GTK clipboard is currently Windows-only. DarkRadiant clipboard is not supported.
