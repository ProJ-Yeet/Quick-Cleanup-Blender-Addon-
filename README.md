# Description
Quick Mesh Cleanup+ (All-in-One) is a Blender addon that performs one-click, batch mesh cleanup on multiple selected objects using presets, fast BMesh operations, and an organized, collapsible UI for topology, normals, shading, and transforms.

As of **v4.0.0** it also handles scene-level housekeeping: purging unused data-blocks and packing/unpacking external resources.

# Features
### Presets
Includes presets to choose from that contains a few game ready default optimizations or lets you save your own custom preset of your choice. **Light**, **Game-Ready** and **Heavy** are built in, and every preset writes the complete option set, so switching presets never leaves stale toggles behind.

<img width="524" height="162" alt="image" src="https://github.com/user-attachments/assets/8431141e-7585-4ba6-b819-8a0ea705fbcc" />

### Options
Offers various options which can be ticked according to desire for cleanup. 
Various Topology, Normals/Data, Shading/Origin, Scene Data and a few more Advanced options are provided
All the options are given in the image below and all are executed on pressing the run button or its shortcut key Ctrl + Alt + Q

<img width="518" height="458" alt="image" src="https://github.com/user-attachments/assets/3fb7d5e9-5859-417f-85ac-ceb9c0ded21c" />
<img width="518" height="498" alt="image" src="https://github.com/user-attachments/assets/f591eb5f-8136-48a3-a26c-a4c5be3ba77a" />

### Scope
Choose whether the cleanup runs on the **Selected** objects, every **Visible** object, or **All in Scene**.

### Scene Data
- **Purge All Unused Data** — recursively deletes every data-block with no users (meshes, materials, images, node groups, actions and so on) and reports how many went.
- **Pack / Unpack Resources** — pack every external file into the .blend, or unpack it back out with a choice of five methods.

### Analyze
A read-only pass that reports tris/quads/ngons, approximate duplicate vertices, non-manifold edges, loose geometry and open boundaries, without touching the mesh.

# Performance
v4.0.0 stays in Object Mode and drives BMesh directly instead of toggling Edit Mode per object, and batches the object-level operators into single calls. Measured headless on Blender 4.5.9, identical workload and identical results:

| Objects | v3 | v4.0.0 |
|---|---|---|
| 100 | 5.4 s | 0.14 s |
| 400 | 138.5 s | 0.46 s |
| 2000 | — | 2.6 s |

The old build got disproportionately slower as objects were added (4x the objects cost 25x the time). v4 scales linearly.

# Installation
- Download the addon ZIP from the GitHub Releases page.
- In Blender, go to Edit → Preferences → Add-ons → Install.
- Select the downloaded ZIP file and click Install Add-on.
- Enable “Quick Mesh Cleanup+ (All-in-One)” in the Add-ons list.
- Open the 3D Viewport, press N to show the Sidebar, and go to the “Quick Cleanup+” tab.

Requires Blender 4.2 or newer. Tested on 4.5 LTS and 5.1.

# Technology
- Implemented in Python using the Blender Python API (bpy).
- Uses BMesh for all topology and normals work, run in Object Mode so no per-object mode switching is needed.
- Object-level operators (transforms, origins, shading, modifier application) are batched into one call for the whole selection.
- Meshes shared between objects are cleaned once, and meshes with shape keys are routed through a single multi-object Edit Mode session so their keys survive.
- Stores configuration as Scene properties so settings persist with your .blend file; the Custom preset lives in add-on preferences so it persists across files.

# Credits
- Addon author: ProJYeet.
- Blender and Python communities for documentation, examples, and inspiration.
- All testers and users who provided feedback and ideas for presets and workflow improvements.
