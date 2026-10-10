<p>
  <a href="https://github.com/ProJ-Yeet/Quick-Cleanup-Blender-Addon-/releases/latest"><img alt="Download the latest release" src="https://img.shields.io/badge/download-latest-e8743b?style=for-the-badge"></a>
  <a href="https://github.com/ProJ-Yeet/Quick-Cleanup-Blender-Addon-/releases"><img alt="Downloads" src="https://img.shields.io/github/downloads/ProJ-Yeet/Quick-Cleanup-Blender-Addon-/total?style=for-the-badge&label=downloads&color=2ea44f"></a>
  <a href="https://ko-fi.com/projyeet"><img alt="Support me on Ko-fi" src="https://ko-fi.com/img/githubbutton_sm.svg" height="28"></a>
</p>
<p>
  <a href="https://www.youtube.com/@proj-yeet"><img alt="YouTube" src="https://img.shields.io/badge/youtube-ProJ--Yeet-ff0000?style=for-the-badge&logo=youtube&logoColor=white"></a>
  <a href="https://discord.gg/epic-unity-rework"><img alt="Discord" src="https://img.shields.io/badge/discord-join%20us-5865f2?style=for-the-badge&logo=discord&logoColor=white"></a>
</p>

### Why support it
The addon is free and will stay free. It is written by one person in spare time, and every speed-up in it was measured on real scenes before it shipped. If it has saved you a few hundred clicks of cleanup, a coffee on [Ko-fi](https://ko-fi.com/projyeet) pays for the hours behind the next version. Never required, always appreciated. Ideas and bug reports are just as welcome on [Discord](https://discord.gg/epic-unity-rework).

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
Choose whether the cleanup runs on the **Selected** objects, every **Visible** object, or **All in Scene**. The panel shows how many objects and vertices the current scope actually covers, so you can see what a run will cost before starting it — **All in Scene** includes meshes hidden inside collections that are switched off, which is usually why a run takes longer than expected.

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

### Why Object Mode BMesh, and not one big Edit Mode pass
For v4.1.0 the obvious next step was tried and measured: select every object, enter Edit Mode once, select all vertices and run each operation a single time, the way you would by hand. On real production scenes it came out **slower** — about 1.2-1.5x on Game-Ready and 2x on Heavy — so it was not shipped.

Once per-object mode switching is gone, what remains is the cost of Blender's own geometry operations, which is identical either way. A single Edit Mode session only adds per-object edit-mesh construction and selection flushes on top. It also silently skips anything not currently visible: on one test scene, "select all, Tab" picked up 8 of 105 mesh objects.

If a run feels slow, the two things that actually dominate are the **Scope** (how many objects it covers, including hidden ones) and **Fill Holes**, which on a dense scene accounted for 80% of a Heavy run on its own.

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
- Meshes shared between objects are cleaned once, and meshes with shape keys are routed through a single multi-object Edit Mode session so their keys survive — collection and object visibility is temporarily revealed for that session and restored afterwards, so shape-keyed meshes in hidden collections are no longer skipped.
- Stores configuration as Scene properties so settings persist with your .blend file; the Custom preset lives in add-on preferences so it persists across files.

# Credits
- Addon author: ProJYeet.
- Blender and Python communities for documentation, examples, and inspiration.
- All testers and users who provided feedback and ideas for presets and workflow improvements.
