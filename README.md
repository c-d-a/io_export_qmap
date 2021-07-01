## .map exporter for Blender

Exports either objects as convex brushes, or individual faces as pyramids. Uses material names for texture assignment and material image size for scaling. Supports UVs both in standard Quake and in Valve220 format (adapted from EricW's implementation for [OBJ2MAP](https://bitbucket.org/khreathor/obj-2-map)). Offers custom grid and precision. Allows saving to clipboard.

The exporter ensures that the brushes are convex and the faces planar. You don't have to triangulate the meshes in advance, but in some cases it can help with UVs (e.g. with mid-edge vertices). There's room for improvement, but it should work fine as is.

Standard format UV export is lossy (no shearing). I don't really expect anyone to be using it over Valve220 anyway, but it should produce decent results for id1-style detailing. Single-axis curves should be fine, no miracles though.

## Installation

Download io_export_qmap.py, then select it under "Edit > Preferences > Add-ons > Install"
