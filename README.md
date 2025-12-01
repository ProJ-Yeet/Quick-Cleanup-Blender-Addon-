# Description
Quick Mesh Cleanup+ (All-in-One) is a Blender addon that performs one-click, batch mesh cleanup on multiple selected objects using presets, fast BMesh operations, and an organized, collapsible UI for topology, normals, shading, and transforms.

# Features
### Presets
Includes presets to choose from that contains a few game ready default optimizations or lets you save your own custom preset of your choice
<img width="524" height="162" alt="image" src="https://github.com/user-attachments/assets/8431141e-7585-4ba6-b819-8a0ea705fbcc" />

### Options
Offers various options which can be ticked according to desire for cleanup. 
Various Topology, Normals/Data, Shading/Origin and a few more Advanced options are provided
All the options are given in the image below and all are executed on pressing the run button or its shortcut key Alt + Ctrl + Q

<img width="518" height="458" alt="image" src="https://github.com/user-attachments/assets/3fb7d5e9-5859-417f-85ac-ceb9c0ded21c" />
<img width="518" height="498" alt="image" src="https://github.com/user-attachments/assets/f591eb5f-8136-48a3-a26c-a4c5be3ba77a" />

# Installation
- Download the addon ZIP from the GitHub Releases page.
- In Blender, go to Edit → Preferences → Add-ons → Install.
- Select the downloaded ZIP file and click Install Add-on.
- Enable “Quick Mesh Cleanup+ (All-in-One)” in the Add-ons list.
- Open the 3D Viewport, press N to show the Sidebar, and go to the “Quick Cleanup+” tab.

# Technology
- Implemented in Python using the Blender Python API (bpy).
- Uses BMesh for core topology and normals operations to improve performance and robustness.
- Relies on Blender’s built-in mesh, shading, and origin operators with safe context overrides.
- Stores configuration as Scene properties so settings persist with your .blend file.

# Credits
- Addon author: ProJYeet.
- Blender and Python communities for documentation, examples, and inspiration.
- All testers and users who provided feedback and ideas for presets and workflow improvements.
