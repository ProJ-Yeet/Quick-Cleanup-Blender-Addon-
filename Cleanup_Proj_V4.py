bl_info = {
    "name": "Quick Mesh Cleanup+ (All-in-One)",
    "author": "ProJYeet",
    "version": (4, 0, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > Quick Cleanup+",
    "description": "Fast batch mesh cleanup: BMesh topology, normals, shading, origins, plus scene data purge and resource pack/unpack",
    "category": "Mesh",
}

import bpy
import bmesh
import math
import time
from contextlib import contextmanager

# ---------------------------------------------------------------------------
# Enum item tables
# ---------------------------------------------------------------------------

QMC_SCOPE_ITEMS = [
    ('SELECTED', "Selected",       "Process the selected mesh objects"),
    ('VISIBLE',  "Visible",        "Process every mesh object visible in the viewport"),
    ('ALL',      "All in Scene",   "Process every mesh object in the view layer, hidden ones included"),
]

QMC_ORIGIN_MODE_ITEMS = [
    ('NONE',                  "Do Nothing",                          ""),
    ('GEOMETRY_TO_ORIGIN',    "Geometry to Origin",                  "Move the mesh data so it sits on the object origin"),
    ('OBJECT_TO_WORLD',       "Object to World Origin",              "Move the whole object to (0, 0, 0), geometry follows"),
    ('ORIGIN_TO_GEOMETRY',    "Origin to Geometry",                  "Move the origin to the bounding box center"),
    ('ORIGIN_TO_CURSOR',      "Origin to 3D Cursor",                 "Set the origin to the 3D cursor"),
    ('ORIGIN_TO_COM_VOLUME',  "Origin to Center of Mass (Volume)",   "Use the volume center for the origin position"),
    ('ORIGIN_TO_COM_SURFACE', "Origin to Center of Mass (Surface)",  "Use the surface center for the origin position"),
]

QMC_SHADE_MODE_ITEMS = [
    ('NONE',   "Do Nothing",  ""),
    ('FLAT',   "Flat",        "Shade every face flat"),
    ('SMOOTH', "Smooth",      "Shade every face smooth"),
    ('AUTO',   "Auto Smooth", "Smooth by angle (adds Blender's Smooth by Angle modifier)"),
]

QMC_DELIMIT_ITEMS = [
    ('NORMAL',   "Normal",   "Do not dissolve across face-normal discontinuities"),
    ('MATERIAL', "Material", "Do not dissolve across material boundaries"),
    ('SEAM',     "Seam",     "Do not dissolve across UV seams"),
    ('SHARP',    "Sharp",    "Do not dissolve across sharp edges"),
    ('UV',       "UVs",      "Do not dissolve across UV island boundaries"),
]

QMC_COMPARE_ITEMS = [
    ('SEAM',  "Seams",         "Do not join triangles across UV seams"),
    ('SHARP', "Sharp",         "Do not join triangles across sharp edges"),
    ('UVS',   "UVs",           "Do not join triangles that would break UVs"),
    ('VCOLS', "Vertex Colors", "Do not join triangles that would break vertex colors"),
]

QMC_UNPACK_METHOD_ITEMS = [
    ('USE_LOCAL',      "Use Local File",        "Use the local file if it exists, otherwise write it"),
    ('WRITE_LOCAL',    "Write Local File",      "Always write to the local //textures folder, overwriting"),
    ('USE_ORIGINAL',   "Use Original File",     "Use the original path if it exists, otherwise write it"),
    ('WRITE_ORIGINAL', "Write Original File",   "Always write to the original path, overwriting"),
    ('REMOVE',         "Remove Pack",           "Drop the packed data without writing anything to disk"),
]

MODE_RESTORE = {
    'OBJECT': 'OBJECT',
    'EDIT_MESH': 'EDIT', 'EDIT_CURVE': 'EDIT', 'EDIT_CURVES': 'EDIT',
    'EDIT_SURFACE': 'EDIT', 'EDIT_TEXT': 'EDIT', 'EDIT_ARMATURE': 'EDIT',
    'EDIT_METABALL': 'EDIT', 'EDIT_LATTICE': 'EDIT', 'EDIT_GREASE_PENCIL': 'EDIT',
    'EDIT_POINT_CLOUD': 'EDIT',
    'POSE': 'POSE', 'SCULPT': 'SCULPT', 'PARTICLE': 'PARTICLE_EDIT',
    'PAINT_WEIGHT': 'WEIGHT_PAINT', 'PAINT_VERTEX': 'VERTEX_PAINT',
    'PAINT_TEXTURE': 'TEXTURE_PAINT', 'PAINT_GREASE_PENCIL': 'PAINT_GREASE_PENCIL',
}

addon_keymaps = []

# ---------------------------------------------------------------------------
# Logging
#
# The log buffer is cleared at the start of every run and capped, so it can no
# longer grow without bound across a session. Console printing is off unless
# debug logging is enabled in the add-on preferences, because printing a few
# thousand lines to the Windows console is itself a noticeable stall.
# ---------------------------------------------------------------------------

_LOG = []
_LOG_MAX = 4000
_DEBUG = False


def log(msg):
    if not _DEBUG:
        return
    if len(_LOG) < _LOG_MAX:
        entry = f"[QMC+] {msg}"
        _LOG.append(entry)
        print(entry)
    elif len(_LOG) == _LOG_MAX:
        _LOG.append("[QMC+] ... log truncated ...")


def warn(msg):
    """Something actually went wrong - always recorded, always printed."""
    entry = f"[QMC+] WARNING: {msg}"
    if len(_LOG) < _LOG_MAX:
        _LOG.append(entry)
    print(entry)


def reset_log(debug_enabled):
    global _DEBUG
    _DEBUG = bool(debug_enabled)
    _LOG.clear()


def dump_log_to_text_editor():
    if not _LOG:
        return
    txt = bpy.data.texts.get("QMC_Log") or bpy.data.texts.new("QMC_Log")
    try:
        txt.clear()
    except Exception:
        while txt.lines:
            txt.lines.remove(txt.lines[0])
    txt.write("\n".join(_LOG) + "\n")


def get_prefs():
    try:
        return bpy.context.preferences.addons[__name__].preferences
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Context helpers
# ---------------------------------------------------------------------------

def find_view3d():
    wm = bpy.context.window_manager
    for window in wm.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        return window, area, region
    return None, None, None


@contextmanager
def view3d_context(context):
    """Run operators against a 3D View, whatever context we were invoked from."""
    area = getattr(context, "area", None)
    if area is not None and area.type == 'VIEW_3D':
        yield
        return
    window, area, region = find_view3d()
    if area is None:
        yield
        return
    with context.temp_override(window=window, area=area, region=region):
        yield


def ensure_object_mode(context):
    if context.mode == 'OBJECT':
        return True
    try:
        bpy.ops.object.mode_set(mode='OBJECT')
        return True
    except Exception as e:
        warn(f"could not leave {context.mode}: {e}")
        return False


def restore_mode(context, stored_mode):
    target = MODE_RESTORE.get(stored_mode)
    if not target or target == context.mode:
        return
    try:
        bpy.ops.object.mode_set(mode=target)
    except Exception as e:
        log(f"could not restore mode '{stored_mode}' -> '{target}': {e}")


def select_objects(context, objs, active=None):
    """Select exactly `objs`. Returns the ones that could actually be selected."""
    try:
        bpy.ops.object.select_all(action='DESELECT')
    except Exception:
        for o in context.view_layer.objects:
            try:
                o.select_set(False)
            except Exception:
                pass
    selected = []
    for o in objs:
        try:
            o.select_set(True)
            selected.append(o)
        except Exception:
            pass  # hidden or not in the view layer
    if selected:
        try:
            context.view_layer.objects.active = active if active in selected else selected[0]
        except Exception:
            pass
    return selected


def view_selected_safe(context):
    window, area, region = find_view3d()
    if area is None:
        return False
    with context.temp_override(window=window, area=area, region=region):
        try:
            bpy.ops.view3d.view_selected(use_all_regions=False)
            return True
        except Exception as e:
            log(f"view_selected failed: {e}")
            return False


# ---------------------------------------------------------------------------
# Mesh data helpers
# ---------------------------------------------------------------------------

def mesh_totals(meshes):
    v = e = f = 0
    for me in meshes:
        v += len(me.vertices)
        e += len(me.edges)
        f += len(me.polygons)
    return v, e, f


def clear_custom_normals(me):
    """Drop custom split normals via the data API (no operator, no context, no mode switch)."""
    attrs = getattr(me, "attributes", None)
    if attrs is not None:
        attr = attrs.get("custom_normal")
        if attr is not None:
            try:
                attrs.remove(attr)
                return True
            except Exception as e:
                log(f"attribute removal of custom_normal failed on {me.name}: {e}")
    if getattr(me, "has_custom_normals", False):
        try:
            me.free_normals_split()
            return True
        except Exception as e:
            log(f"free_normals_split failed on {me.name}: {e}")
    return False


def remove_auto_smooth_modifier(obj):
    """Blender's 'Smooth by Angle' is a geometry-nodes modifier, not its own type."""
    removed = 0
    for mod in list(obj.modifiers):
        if mod.type != 'NODES':
            continue
        node_group = getattr(mod, "node_group", None)
        name = node_group.name if node_group else ""
        if "Smooth by Angle" in name or "Smooth by Angle" in mod.name:
            try:
                obj.modifiers.remove(mod)
                removed += 1
            except Exception as e:
                log(f"could not remove auto-smooth modifier on {obj.name}: {e}")
    return removed


def set_mesh_shading(me, smooth):
    if smooth and hasattr(me, "shade_smooth"):
        me.shade_smooth()
        return
    if not smooth and hasattr(me, "shade_flat"):
        me.shade_flat()
        return
    count = len(me.polygons)
    if count:
        me.polygons.foreach_set("use_smooth", [smooth] * count)
        me.update()


def remove_empty_vertex_groups(obj):
    """Drop vertex groups that no vertex is weighted to."""
    if not obj.vertex_groups or obj.type != 'MESH':
        return 0
    used = set()
    group_count = len(obj.vertex_groups)
    for v in obj.data.vertices:
        for g in v.groups:
            used.add(g.group)
        if len(used) == group_count:
            return 0  # every group is in use, stop scanning early
    removed = 0
    for vg in [g for g in obj.vertex_groups if g.index not in used]:
        obj.vertex_groups.remove(vg)
        removed += 1
    return removed


# ---------------------------------------------------------------------------
# Options snapshot
#
# Reading a bpy property is an RNA lookup. Doing that inside a loop over every
# mesh is measurable, so the whole configuration is copied into a plain object
# once per run and the hot loop only touches Python attributes.
# ---------------------------------------------------------------------------

class Options:
    pass


CLEANUP_OPTION_KEYS = (
    "select_all",
    "merge_vertices", "merge_distance",
    "dissolve_degenerate", "degenerate_distance",
    "delete_loose",
    "fix_non_manifold",
    "fill_holes", "fill_holes_sides",
    "dissolve_limited", "dissolve_angle", "dissolve_delimit",
    "tris_to_quads", "tris_to_quads_angle", "tris_to_quads_compare",
    "triangulate",
    "recalc_normals", "recalc_inside",
    "clear_sharp", "clear_seams",
)


def options_from_scene(scene):
    o = Options()
    for key in CLEANUP_OPTION_KEYS:
        setattr(o, key, getattr(scene, "qmc_" + key))
    return o


# ---------------------------------------------------------------------------
# Core BMesh cleanup
#
# Pure bmesh - no bpy.ops, no mode switching, no depsgraph churn. This is what
# lets the add-on stay in Object Mode for the whole run.
# ---------------------------------------------------------------------------

def cleanup_bmesh(bm, o, name="mesh"):
    def verts():
        return bm.verts if o.select_all else [v for v in bm.verts if v.select]

    def edges():
        return bm.edges if o.select_all else [e for e in bm.edges if e.select]

    def faces():
        return bm.faces if o.select_all else [f for f in bm.faces if f.select]

    if o.select_all:
        for v in bm.verts:
            v.select_set(True)
        # Without this flush, edges and faces stay unselected and every
        # face-based operation silently does nothing.
        bm.select_flush(True)

    if o.merge_vertices:
        target = verts()
        if target:
            try:
                bmesh.ops.remove_doubles(bm, verts=target, dist=o.merge_distance)
            except Exception as e:
                warn(f"{name}: remove_doubles failed: {e}")

    if o.dissolve_degenerate:
        try:
            bmesh.ops.dissolve_degenerate(bm, dist=o.degenerate_distance, edges=edges())
        except Exception as e:
            warn(f"{name}: dissolve_degenerate failed: {e}")

    if o.fix_non_manifold:
        # An edge with one face is a *boundary*, not a defect. The old check
        # used `not e.is_manifold`, which is True for boundaries too, so
        # enabling this used to shred every open mesh. Only edges shared by
        # three or more faces are actually non-manifold.
        try:
            bad = [e for e in edges() if len(e.link_faces) > 2]
            if bad:
                bmesh.ops.delete(bm, geom=bad, context='EDGES')
                log(f"{name}: removed {len(bad)} non-manifold edges")
        except Exception as e:
            warn(f"{name}: fix non-manifold failed: {e}")

    if o.delete_loose:
        # bmesh.ops.delete only looks at the geometry type matching `context`,
        # so this needs three passes, not one mixed list.
        try:
            wire_edges = [e for e in edges() if not e.link_faces]
            if wire_edges:
                bmesh.ops.delete(bm, geom=wire_edges, context='EDGES')
            stray_verts = [v for v in verts() if not v.link_edges and not v.link_faces]
            if stray_verts:
                bmesh.ops.delete(bm, geom=stray_verts, context='VERTS')
        except Exception as e:
            warn(f"{name}: delete loose failed: {e}")

    if o.fill_holes:
        try:
            boundary = [e for e in edges() if len(e.link_faces) == 1]
            if boundary:
                bmesh.ops.holes_fill(bm, edges=boundary, sides=o.fill_holes_sides)
        except Exception as e:
            warn(f"{name}: fill holes failed: {e}")

    if o.dissolve_limited:
        try:
            bmesh.ops.dissolve_limit(
                bm,
                edges=edges(),
                verts=verts(),
                angle_limit=math.radians(o.dissolve_angle),
                use_dissolve_boundaries=False,
                delimit=set(o.dissolve_delimit),
            )
        except Exception as e:
            warn(f"{name}: dissolve_limit failed: {e}")

    if o.tris_to_quads:
        try:
            tris = [f for f in faces() if len(f.verts) == 3]
            if tris:
                cmp_flags = set(o.tris_to_quads_compare)
                kwargs = dict(
                    faces=tris,
                    angle_face_threshold=o.tris_to_quads_angle,
                    angle_shape_threshold=o.tris_to_quads_angle,
                    cmp_seam='SEAM' in cmp_flags,
                    cmp_sharp='SHARP' in cmp_flags,
                    cmp_uvs='UVS' in cmp_flags,
                    cmp_vcols='VCOLS' in cmp_flags,
                )
                try:
                    bmesh.ops.join_triangles(bm, **kwargs)
                except TypeError:
                    # older/newer signatures - fall back to the required args
                    bmesh.ops.join_triangles(
                        bm, faces=tris,
                        angle_face_threshold=o.tris_to_quads_angle,
                        angle_shape_threshold=o.tris_to_quads_angle,
                    )
                log(f"{name}: joined from {len(tris)} triangles")
        except Exception as e:
            warn(f"{name}: join_triangles failed: {e}")

    if o.triangulate:
        try:
            target = faces()
            if target:
                bmesh.ops.triangulate(bm, faces=target, quad_method='BEAUTY', ngon_method='BEAUTY')
        except Exception as e:
            warn(f"{name}: triangulate failed: {e}")

    if o.clear_sharp or o.clear_seams:
        for e in bm.edges:
            if o.clear_sharp:
                e.smooth = True
            if o.clear_seams:
                e.seam = False

    if o.recalc_normals:
        try:
            target = faces()
            if target:
                bmesh.ops.recalc_face_normals(bm, faces=target)
                if o.recalc_inside:
                    bmesh.ops.reverse_faces(bm, faces=faces())
            bm.normal_update()
        except Exception as e:
            warn(f"{name}: recalc normals failed: {e}")


def analyze_bmesh(bm, merge_distance):
    """Read-only pass used by the Analyze operator."""
    tris = quads = ngons = 0
    for f in bm.faces:
        n = len(f.verts)
        if n == 3:
            tris += 1
        elif n == 4:
            quads += 1
        else:
            ngons += 1
    non_manifold = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    boundary = sum(1 for e in bm.edges if len(e.link_faces) == 1)
    wire = sum(1 for e in bm.edges if not e.link_faces)
    stray = sum(1 for v in bm.verts if not v.link_edges and not v.link_faces)

    doubles = 0
    if merge_distance > 0.0 and len(bm.verts) <= 500000:
        buckets = {}
        inv = 1.0 / merge_distance
        for v in bm.verts:
            key = (int(v.co.x * inv), int(v.co.y * inv), int(v.co.z * inv))
            if key in buckets:
                doubles += 1
            else:
                buckets[key] = True
    return {
        "tris": tris, "quads": quads, "ngons": ngons,
        "non_manifold": non_manifold, "boundary": boundary,
        "wire": wire, "stray": stray, "doubles": doubles,
    }


# ---------------------------------------------------------------------------
# Target gathering
# ---------------------------------------------------------------------------

def gather_targets(context, scope):
    view_layer = context.view_layer
    if scope == 'ALL':
        candidates = [o for o in view_layer.objects if o.type == 'MESH']
    elif scope == 'VISIBLE':
        candidates = [o for o in view_layer.objects if o.type == 'MESH' and o.visible_get()]
    else:
        candidates = [o for o in context.selected_objects if o.type == 'MESH']

    targets = []
    skipped_linked = 0
    for o in candidates:
        if o.data is None:
            continue
        if o.library is not None or o.data.library is not None:
            skipped_linked += 1
            continue
        targets.append(o)
    if skipped_linked:
        log(f"skipped {skipped_linked} linked (library) object(s)")
    return targets


# ---------------------------------------------------------------------------
# Batched phases
#
# Object-level operators act on the whole selection at once. Calling them once
# for N objects instead of N times is the single biggest win when the scene is
# large - each call otherwise triggers its own depsgraph update and undo push.
# ---------------------------------------------------------------------------

def phase_apply_modifiers(context, targets, decimate_ratio, apply_modifiers):
    if not apply_modifiers and decimate_ratio >= 1.0:
        return 0

    workable, skipped = [], []
    for o in targets:
        if o.data.shape_keys is not None:
            skipped.append(o.name)
            continue
        workable.append(o)
    if skipped:
        warn(f"modifier/decimate pass skipped {len(skipped)} object(s) with shape keys: "
             f"{', '.join(skipped[:5])}{' ...' if len(skipped) > 5 else ''}")

    decimated = []
    if decimate_ratio < 1.0:
        for o in workable:
            try:
                mod = o.modifiers.new(name="QMC_Decimate", type='DECIMATE')
                mod.ratio = decimate_ratio
                decimated.append(o)
            except Exception as e:
                warn(f"{o.name}: could not add decimate modifier: {e}")

    if not apply_modifiers:
        # Decimate only. convert() would flatten the user's whole modifier
        # stack as a side effect, which they did not ask for, so the temporary
        # decimate modifier is applied on its own.
        done = 0
        for o in decimated:
            try:
                context.view_layer.objects.active = o
                bpy.ops.object.modifier_apply(modifier="QMC_Decimate")
                done += 1
            except Exception as e:
                warn(f"{o.name}: decimate apply failed: {e}")
                try:
                    o.modifiers.remove(o.modifiers["QMC_Decimate"])
                except Exception:
                    pass
        log(f"decimated {done} object(s) to ratio {decimate_ratio}")
        return done

    todo = [o for o in workable if o.modifiers]
    if not todo:
        return 0

    selected = select_objects(context, todo)
    if not selected:
        return 0
    with view3d_context(context):
        try:
            bpy.ops.object.convert(target='MESH')
            log(f"applied modifiers on {len(selected)} object(s) in one pass")
            return len(selected)
        except Exception as e:
            warn(f"batch modifier apply failed ({e}), falling back to per-object")

    done = 0
    for o in todo:
        try:
            context.view_layer.objects.active = o
        except Exception:
            continue
        for mod_name in [m.name for m in o.modifiers]:
            try:
                bpy.ops.object.modifier_apply(modifier=mod_name)
            except Exception as e:
                warn(f"{o.name}: modifier '{mod_name}' failed to apply: {e}")
        done += 1
    return done


def phase_apply_transforms(context, targets, loc, rot, scale):
    if not (loc or rot or scale):
        return 0
    selected = select_objects(context, targets)
    if not selected:
        return 0
    with view3d_context(context):
        try:
            bpy.ops.object.transform_apply(location=loc, rotation=rot, scale=scale,
                                           properties=False, isolate_users=True)
        except TypeError:
            bpy.ops.object.transform_apply(location=loc, rotation=rot, scale=scale)
        except Exception as e:
            warn(f"transform apply failed: {e}")
            return 0
    log(f"applied transforms on {len(selected)} object(s) in one pass")
    return len(selected)


def phase_shading(context, targets, shade_mode, auto_smooth_angle):
    if shade_mode == 'NONE':
        return 0

    if shade_mode == 'AUTO':
        # Drop any existing Smooth by Angle modifier first so repeated runs
        # cannot stack duplicates on the same object.
        for o in targets:
            remove_auto_smooth_modifier(o)
        selected = select_objects(context, targets)
        if not selected:
            return 0
        with view3d_context(context):
            try:
                bpy.ops.object.shade_auto_smooth(angle=auto_smooth_angle)
            except TypeError:
                # Older builds do not expose the angle argument.
                try:
                    bpy.ops.object.shade_auto_smooth()
                    warn("this Blender build ignores the Auto Smooth Angle argument")
                except Exception as e:
                    warn(f"shade_auto_smooth failed: {e}")
                    return 0
            except Exception as e:
                warn(f"shade_auto_smooth failed: {e}")
                return 0
        return len(selected)

    smooth = (shade_mode == 'SMOOTH')
    done = 0
    for me in {o.data for o in targets}:
        try:
            set_mesh_shading(me, smooth)
            done += 1
        except Exception as e:
            warn(f"{me.name}: shading failed: {e}")
    for o in targets:
        remove_auto_smooth_modifier(o)
    return done


def phase_origin(context, targets, origin_mode):
    if origin_mode == 'NONE':
        return 0

    if origin_mode == 'OBJECT_TO_WORLD':
        for o in targets:
            o.location = (0.0, 0.0, 0.0)
        return len(targets)

    op_args = {
        'GEOMETRY_TO_ORIGIN':    dict(type='GEOMETRY_ORIGIN'),
        'ORIGIN_TO_GEOMETRY':    dict(type='ORIGIN_GEOMETRY', center='BOUNDS'),
        'ORIGIN_TO_CURSOR':      dict(type='ORIGIN_CURSOR'),
        'ORIGIN_TO_COM_VOLUME':  dict(type='ORIGIN_CENTER_OF_MASS', center='VOLUME'),
        'ORIGIN_TO_COM_SURFACE': dict(type='ORIGIN_CENTER_OF_MASS', center='SURFACE'),
    }.get(origin_mode)
    if op_args is None:
        return 0

    selected = select_objects(context, targets)
    if not selected:
        return 0
    with view3d_context(context):
        try:
            bpy.ops.object.origin_set(**op_args)
        except Exception as e:
            warn(f"origin_set failed: {e}")
            return 0
    log(f"set origin on {len(selected)} object(s) in one pass")
    return len(selected)


def phase_material_slots(context, targets):
    selected = select_objects(context, targets)
    if not selected:
        return 0
    with view3d_context(context):
        try:
            bpy.ops.object.material_slot_remove_unused()
            return len(selected)
        except Exception as e:
            warn(f"remove unused material slots failed: {e}")
    return 0


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

PRESET_KEYS = (
    "scope",
    "select_all", "merge_vertices", "merge_distance",
    "dissolve_degenerate", "degenerate_distance",
    "dissolve_limited", "dissolve_angle", "dissolve_delimit",
    "tris_to_quads", "tris_to_quads_angle", "tris_to_quads_compare",
    "triangulate", "delete_loose", "fill_holes", "fill_holes_sides",
    "fix_non_manifold",
    "recalc_normals", "recalc_inside", "reset_vectors",
    "clear_split_normals", "clear_sharp", "clear_seams",
    "origin_mode", "shade_mode", "auto_smooth_angle",
    "apply_loc", "apply_rot", "apply_scale", "apply_modifiers",
    "decimate_ratio", "make_single_user",
    "remove_unused_materials", "remove_empty_vgroups", "rename_data",
    "view_selected",
)


def save_custom_preset_from_scene(scene):
    prefs = get_prefs()
    if prefs is None:
        return False
    for key in PRESET_KEYS:
        setattr(prefs, "custom_" + key, getattr(scene, "qmc_" + key))
    return True


def apply_custom_preset_to_scene(scene):
    prefs = get_prefs()
    if prefs is None:
        return False
    for key in PRESET_KEYS:
        setattr(scene, "qmc_" + key, getattr(prefs, "custom_" + key))
    return True


# Every preset writes the full option set, so switching presets can no longer
# leave stale toggles behind from whatever was configured before.
PRESET_BASE = {
    "select_all": True,
    "merge_vertices": True, "merge_distance": 0.0001,
    "dissolve_degenerate": False, "degenerate_distance": 0.0001,
    "dissolve_limited": False, "dissolve_angle": 5.0, "dissolve_delimit": {'NORMAL'},
    "tris_to_quads": False, "tris_to_quads_angle": 0.698132,
    "tris_to_quads_compare": {'SEAM', 'SHARP'},
    "triangulate": False,
    "delete_loose": True,
    "fill_holes": False, "fill_holes_sides": 4,
    "fix_non_manifold": False,
    "recalc_normals": True, "recalc_inside": False,
    "reset_vectors": False, "clear_split_normals": False,
    "clear_sharp": False, "clear_seams": False,
    "origin_mode": 'NONE', "shade_mode": 'NONE', "auto_smooth_angle": 0.523599,
    "apply_loc": False, "apply_rot": False, "apply_scale": False,
    "apply_modifiers": False, "decimate_ratio": 1.0,
    "make_single_user": True,
    "remove_unused_materials": False, "remove_empty_vgroups": False,
    "rename_data": False, "view_selected": False,
}

PRESETS = {
    'LIGHT': {},
    'GAME': {
        "merge_distance": 0.0008,
        "delete_loose": True,
        "dissolve_degenerate": True,
        "tris_to_quads": True,
        "tris_to_quads_angle": 0.174533,
        "recalc_normals": True,
        "clear_split_normals": True,
        "shade_mode": 'AUTO',
        "apply_rot": True, "apply_scale": True,
        "remove_unused_materials": True,
        "remove_empty_vgroups": True,
    },
    'HEAVY': {
        "merge_distance": 0.002,
        "dissolve_degenerate": True,
        "dissolve_limited": True,
        "dissolve_angle": 5.0,
        "tris_to_quads": True,
        "tris_to_quads_angle": 0.523599,
        "delete_loose": True,
        "fix_non_manifold": True,
        "fill_holes": True,
        "clear_split_normals": True,
        "recalc_normals": True,
        "shade_mode": 'AUTO',
        "remove_unused_materials": True,
        "remove_empty_vgroups": True,
    },
}


def set_preset(scene, preset_name):
    if preset_name == 'CUSTOM':
        return apply_custom_preset_to_scene(scene)
    overrides = PRESETS.get(preset_name)
    if overrides is None:
        return False
    values = dict(PRESET_BASE)
    values.update(overrides)
    for key, value in values.items():
        setattr(scene, "qmc_" + key, value)
    return True


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

class MESH_OT_qmc_preset(bpy.types.Operator):
    bl_idname = "mesh.qmc_preset"
    bl_label = "Apply Cleanup Preset"
    bl_description = "Apply a cleanup preset configuration"
    bl_options = {'REGISTER', 'UNDO'}

    preset: bpy.props.StringProperty(default='LIGHT')

    def execute(self, context):
        if not set_preset(context.scene, self.preset):
            self.report({'WARNING'}, f"Preset '{self.preset}' could not be applied.")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Preset '{self.preset}' applied.")
        return {'FINISHED'}


class MESH_OT_qmc_save_custom_preset(bpy.types.Operator):
    bl_idname = "mesh.qmc_save_custom_preset"
    bl_label = "Save Custom Preset"
    bl_description = "Save the current settings into the Custom preset slot (persists across .blend files)"

    def execute(self, context):
        if not save_custom_preset_from_scene(context.scene):
            self.report({'ERROR'}, "Add-on preferences unavailable - install the add-on rather than running it from the Text Editor.")
            return {'CANCELLED'}
        self.report({'INFO'}, "Custom preset saved.")
        return {'FINISHED'}


class MESH_OT_qmc_analyze(bpy.types.Operator):
    bl_idname = "mesh.qmc_analyze"
    bl_label = "Analyze Meshes"
    bl_description = "Report what a cleanup would find, without changing anything"

    def execute(self, context):
        prefs = get_prefs()
        reset_log(getattr(prefs, "debug_logging", False) if prefs else False)
        scene = context.scene
        targets = gather_targets(context, scene.qmc_scope)
        if not targets:
            self.report({'ERROR'}, "No editable mesh objects found for the current scope.")
            return {'CANCELLED'}

        totals = {"tris": 0, "quads": 0, "ngons": 0, "non_manifold": 0,
                  "boundary": 0, "wire": 0, "stray": 0, "doubles": 0}
        meshes = {o.data for o in targets}
        for me in meshes:
            bm = bmesh.new()
            try:
                bm.from_mesh(me)
                for key, value in analyze_bmesh(bm, scene.qmc_merge_distance).items():
                    totals[key] += value
            except Exception as e:
                warn(f"{me.name}: analyze failed: {e}")
            finally:
                bm.free()

        verts, edges, faces = mesh_totals(meshes)
        report = (f"{len(targets)} obj / {len(meshes)} mesh | "
                  f"{verts:,}v {edges:,}e {faces:,}f | "
                  f"tris {totals['tris']:,} quads {totals['quads']:,} ngons {totals['ngons']:,} | "
                  f"~doubles {totals['doubles']:,} | non-manifold {totals['non_manifold']:,} | "
                  f"loose v/e {totals['stray']:,}/{totals['wire']:,} | open edges {totals['boundary']:,}")
        scene.qmc_last_report = report
        log(report)
        self.report({'INFO'}, report)
        return {'FINISHED'}


class MESH_OT_qmc_purge_unused(bpy.types.Operator):
    bl_idname = "mesh.qmc_purge_unused"
    bl_label = "Purge All Unused Data"
    bl_description = ("Delete every data-block with no users - meshes, materials, images, node groups, "
                      "actions and so on. Recursive, so data freed by the purge is purged too")
    bl_options = {'REGISTER', 'UNDO'}

    do_local_ids: bpy.props.BoolProperty(
        name="Local Data-Blocks", default=True,
        description="Purge unused data-blocks that live in this file")
    do_linked_ids: bpy.props.BoolProperty(
        name="Linked Data-Blocks", default=True,
        description="Purge unused data-blocks that came from linked libraries")
    do_recursive: bpy.props.BoolProperty(
        name="Recursive", default=True,
        description="Keep purging until nothing new becomes unused")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=320)

    def draw(self, context):
        layout = self.layout
        layout.label(text="This permanently deletes unused data-blocks.", icon='ERROR')
        layout.label(text="Undo works, but saving afterwards makes it final.")
        layout.separator()
        layout.prop(self, "do_local_ids")
        layout.prop(self, "do_linked_ids")
        layout.prop(self, "do_recursive")

    def execute(self, context):
        before = sum(len(getattr(bpy.data, coll)) for coll in
                     ("meshes", "materials", "images", "node_groups", "actions",
                      "armatures", "curves", "textures", "objects", "collections"))
        try:
            removed = bpy.data.orphans_purge(
                do_local_ids=self.do_local_ids,
                do_linked_ids=self.do_linked_ids,
                do_recursive=self.do_recursive,
            )
        except TypeError:
            removed = bpy.data.orphans_purge()
        except Exception as e:
            self.report({'ERROR'}, f"Purge failed: {e}")
            return {'CANCELLED'}

        after = sum(len(getattr(bpy.data, coll)) for coll in
                    ("meshes", "materials", "images", "node_groups", "actions",
                     "armatures", "curves", "textures", "objects", "collections"))
        msg = f"Purged {removed} unused data-block(s) ({before - after} across tracked collections)."
        context.scene.qmc_last_report = msg
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class MESH_OT_qmc_pack_resources(bpy.types.Operator):
    bl_idname = "mesh.qmc_pack_resources"
    bl_label = "Pack All Resources"
    bl_description = "Pack every external file (images, sounds, fonts, caches) into the .blend"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            bpy.ops.file.pack_all()
        except Exception as e:
            self.report({'ERROR'}, f"Pack failed: {e}")
            return {'CANCELLED'}
        packed = sum(1 for img in bpy.data.images if img.packed_file)
        msg = f"Packed resources into the .blend ({packed} image(s) now packed)."
        context.scene.qmc_last_report = msg
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class MESH_OT_qmc_unpack_resources(bpy.types.Operator):
    bl_idname = "mesh.qmc_unpack_resources"
    bl_label = "Unpack All Resources"
    bl_description = "Unpack every packed file back out to disk"
    bl_options = {'REGISTER', 'UNDO'}

    method: bpy.props.EnumProperty(
        name="Method", items=QMC_UNPACK_METHOD_ITEMS, default='USE_LOCAL',
        description="How to resolve files that already exist on disk")

    def invoke(self, context, event):
        self.method = context.scene.qmc_unpack_method
        return context.window_manager.invoke_props_dialog(self, width=340)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "method")
        if self.method in {'WRITE_LOCAL', 'WRITE_ORIGINAL'}:
            layout.label(text="Existing files on disk will be overwritten.", icon='ERROR')
        elif self.method == 'REMOVE':
            layout.label(text="Packed data is discarded, not written out.", icon='ERROR')

    def execute(self, context):
        if not bpy.data.is_saved and self.method in {'USE_LOCAL', 'WRITE_LOCAL'}:
            self.report({'ERROR'}, "Save the .blend first - local unpack paths are relative to it.")
            return {'CANCELLED'}
        try:
            bpy.ops.file.unpack_all(method=self.method)
        except Exception as e:
            self.report({'ERROR'}, f"Unpack failed: {e}")
            return {'CANCELLED'}
        msg = f"Unpacked all resources ({self.method})."
        context.scene.qmc_last_report = msg
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class MESH_OT_qmc_dump_log(bpy.types.Operator):
    bl_idname = "mesh.qmc_dump_log"
    bl_label = "Write Log to Text Editor"
    bl_description = "Write the last run's log into a QMC_Log text block"

    def execute(self, context):
        if not _LOG:
            self.report({'WARNING'}, "Log is empty. Enable debug logging in the add-on preferences first.")
            return {'CANCELLED'}
        dump_log_to_text_editor()
        self.report({'INFO'}, f"Wrote {len(_LOG)} line(s) to text block 'QMC_Log'.")
        return {'FINISHED'}


class MESH_OT_quick_cleanup_all_in_one(bpy.types.Operator):
    bl_idname = "mesh.quick_cleanup_all_in_one"
    bl_label = "Run Quick Cleanup+"
    bl_description = "Run batch cleanup on the targeted mesh objects"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        prefs = get_prefs()
        reset_log(getattr(prefs, "debug_logging", False) if prefs else False)

        t0 = time.perf_counter()
        scene = context.scene

        targets = gather_targets(context, scene.qmc_scope)
        if not targets:
            self.report({'ERROR'}, "No editable mesh objects found for the current scope.")
            return {'CANCELLED'}

        original_mode = context.mode
        original_active = context.view_layer.objects.active
        original_selection = list(context.selected_objects)

        if not ensure_object_mode(context):
            self.report({'ERROR'}, "Could not switch to Object Mode.")
            return {'CANCELLED'}

        v0, e0, f0 = mesh_totals({o.data for o in targets})
        log(f"start: {len(targets)} object(s), {v0} verts / {f0} faces")

        # -- single-user / shared-data handling -----------------------------
        if scene.qmc_make_single_user:
            copied = 0
            for o in targets:
                if o.data.users > 1:
                    o.data = o.data.copy()
                    copied += 1
            if copied:
                log(f"made {copied} mesh data-block(s) single user")

        # -- modifiers + decimate (batched) ---------------------------------
        phase_apply_modifiers(context, targets, scene.qmc_decimate_ratio, scene.qmc_apply_modifiers)

        # -- transforms (batched) -------------------------------------------
        phase_apply_transforms(context, targets, scene.qmc_apply_loc,
                               scene.qmc_apply_rot, scene.qmc_apply_scale)

        # Rebuild the mesh map after the modifier pass - convert() replaces
        # object data, so a map built earlier would point at stale meshes.
        mesh_to_objs = {}
        for o in targets:
            mesh_to_objs.setdefault(o.data, []).append(o)
        shared = sum(1 for me, objs in mesh_to_objs.items() if me.users > len(objs))
        if shared:
            warn(f"{shared} mesh data-block(s) are shared with objects outside the "
                 f"target set; enable 'Make Single User' to avoid affecting them")

        opts = options_from_scene(scene)

        # Meshes with shape keys cannot round-trip through bm.to_mesh() without
        # losing the keys, so they go through a single multi-object Edit Mode
        # session instead - still one mode switch for the whole batch.
        shape_key_meshes = {me: objs for me, objs in mesh_to_objs.items() if me.shape_keys is not None}
        plain_meshes = {me: objs for me, objs in mesh_to_objs.items() if me.shape_keys is None}

        cleaned, failed = 0, []
        wm = context.window_manager
        total = len(mesh_to_objs)
        step = max(1, total // 100)
        try:
            wm.progress_begin(0, total)
        except Exception:
            pass

        # -- fast path: object-mode BMesh, no operators, no mode switching --
        for idx, me in enumerate(plain_meshes, 1):
            bm = bmesh.new()
            try:
                bm.from_mesh(me)
                cleanup_bmesh(bm, opts, me.name)
                bm.to_mesh(me)
                cleaned += 1
            except Exception as e:
                warn(f"{me.name}: cleanup failed: {e}")
                failed.append(me.name)
            finally:
                bm.free()
            try:
                me.update()
            except Exception:
                pass
            if idx % step == 0:
                try:
                    wm.progress_update(idx)
                except Exception:
                    pass

        # -- shape-key path: one multi-object edit session -------------------
        if shape_key_meshes:
            sk_objs = [objs[0] for objs in shape_key_meshes.values()]
            selected = select_objects(context, sk_objs)
            for o in sk_objs:
                if o not in selected:
                    warn(f"{o.name}: has shape keys and is not selectable (hidden?), skipped")
                    failed.append(o.data.name)
            entered = False
            if selected:
                with view3d_context(context):
                    try:
                        bpy.ops.object.mode_set(mode='EDIT')
                        entered = True
                    except Exception as e:
                        warn(f"could not enter Edit Mode for shape-keyed meshes: {e}")
            if entered:
                for o in selected:
                    me = o.data
                    try:
                        bm = bmesh.from_edit_mesh(me)
                        cleanup_bmesh(bm, opts, me.name)
                        bmesh.update_edit_mesh(me, loop_triangles=True, destructive=True)
                        cleaned += 1
                    except Exception as e:
                        warn(f"{me.name}: cleanup failed: {e}")
                        failed.append(me.name)
                with view3d_context(context):
                    try:
                        bpy.ops.object.mode_set(mode='OBJECT')
                    except Exception as e:
                        warn(f"could not leave Edit Mode: {e}")
            else:
                failed.extend(o.data.name for o in selected)

        try:
            wm.progress_end()
        except Exception:
            pass

        # -- per-mesh data cleanup (pure data API, no operators) ------------
        if scene.qmc_clear_split_normals or scene.qmc_reset_vectors:
            cleared = 0
            for me in mesh_to_objs:
                if clear_custom_normals(me):
                    cleared += 1
            log(f"cleared custom split normals on {cleared} mesh(es)")

        if scene.qmc_rename_data:
            for o in targets:
                if o.data.name != o.name:
                    try:
                        o.data.name = o.name
                    except Exception:
                        pass

        if scene.qmc_remove_empty_vgroups:
            removed = sum(remove_empty_vertex_groups(o) for o in targets)
            if removed:
                log(f"removed {removed} empty vertex group(s)")

        if scene.qmc_remove_unused_materials:
            phase_material_slots(context, targets)

        # -- shading + origin (batched) -------------------------------------
        phase_shading(context, targets, scene.qmc_shade_mode, scene.qmc_auto_smooth_angle)
        phase_origin(context, targets, scene.qmc_origin_mode)

        # -- restore selection / active / mode ------------------------------
        select_objects(context, original_selection or targets, active=original_active)
        if original_active is not None:
            try:
                context.view_layer.objects.active = original_active
            except Exception:
                pass
        restore_mode(context, original_mode)

        if scene.qmc_view_selected and not view_selected_safe(context):
            log("view_selected: no 3D View available")

        v1, e1, f1 = mesh_totals({o.data for o in targets})
        dt = time.perf_counter() - t0
        report = (f"Cleaned {cleaned}/{len(mesh_to_objs)} mesh(es) on {len(targets)} object(s) in {dt:.2f}s | "
                  f"verts {v0:,}->{v1:,} ({v1 - v0:+,}) | faces {f0:,}->{f1:,} ({f1 - f0:+,})")
        if failed:
            report += f" | failed: {', '.join(failed[:5])}{' ...' if len(failed) > 5 else ''}"
        scene.qmc_last_report = report
        log(report)

        if _DEBUG:
            try:
                dump_log_to_text_editor()
            except Exception as e:
                print(f"[QMC+] could not write log text block: {e}")

        self.report({'WARNING'} if failed else {'INFO'}, report)
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

def section_header(layout, scene, prop, text):
    icon = 'TRIA_DOWN' if getattr(scene, prop) else 'TRIA_RIGHT'
    layout.prop(scene, prop, icon=icon, emboss=False, text=text)
    return getattr(scene, prop)


class VIEW3D_PT_quick_cleanup_panel(bpy.types.Panel):
    bl_label = "Quick Mesh Cleanup+"
    bl_idname = "VIEW3D_PT_quick_cleanup_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Quick Cleanup+'

    def draw(self, context):
        scene = context.scene
        layout = self.layout

        layout.label(text="Presets:")
        row = layout.row(align=True)
        row.operator("mesh.qmc_preset", text="Light").preset = 'LIGHT'
        row.operator("mesh.qmc_preset", text="Game-Ready").preset = 'GAME'
        row.operator("mesh.qmc_preset", text="Heavy").preset = 'HEAVY'
        row = layout.row(align=True)
        row.operator("mesh.qmc_preset", text="Custom").preset = 'CUSTOM'
        row.operator("mesh.qmc_save_custom_preset", text="Save")

        layout.separator()
        layout.prop(scene, "qmc_scope", text="Scope")
        layout.separator()

        # --- Topology ---
        if section_header(layout, scene, "qmc_ui_show_topology", "Topology"):
            col = layout.box().column(align=True)
            col.prop(scene, "qmc_select_all")
            col.prop(scene, "qmc_merge_vertices")
            if scene.qmc_merge_vertices:
                col.prop(scene, "qmc_merge_distance")
            col.prop(scene, "qmc_dissolve_degenerate")
            if scene.qmc_dissolve_degenerate:
                col.prop(scene, "qmc_degenerate_distance")
            col.prop(scene, "qmc_delete_loose")
            col.prop(scene, "qmc_fix_non_manifold")
            col.prop(scene, "qmc_fill_holes")
            if scene.qmc_fill_holes:
                col.prop(scene, "qmc_fill_holes_sides")
            col.separator()
            col.prop(scene, "qmc_dissolve_limited")
            if scene.qmc_dissolve_limited:
                col.prop(scene, "qmc_dissolve_angle")
                col.label(text="Do not dissolve across:")
                col.prop(scene, "qmc_dissolve_delimit", text="")
            col.separator()
            col.prop(scene, "qmc_tris_to_quads")
            if scene.qmc_tris_to_quads:
                col.prop(scene, "qmc_tris_to_quads_angle")
                col.label(text="Preserve:")
                col.prop(scene, "qmc_tris_to_quads_compare", text="")
            col.prop(scene, "qmc_triangulate")

        # --- Normals / Data ---
        if section_header(layout, scene, "qmc_ui_show_normals", "Normals / Data"):
            col = layout.box().column(align=True)
            col.prop(scene, "qmc_recalc_normals")
            if scene.qmc_recalc_normals:
                col.prop(scene, "qmc_recalc_inside")
            col.prop(scene, "qmc_clear_split_normals")
            sub = col.row()
            sub.enabled = not scene.qmc_clear_split_normals
            sub.prop(scene, "qmc_reset_vectors")
            col.prop(scene, "qmc_clear_sharp")
            col.prop(scene, "qmc_clear_seams")

        # --- Shading / Origin ---
        if section_header(layout, scene, "qmc_ui_show_shading", "Shading / Origin"):
            col = layout.box().column(align=True)
            col.prop(scene, "qmc_shade_mode", text="Shade Mode")
            if scene.qmc_shade_mode == 'AUTO':
                col.prop(scene, "qmc_auto_smooth_angle", text="Angle")
            col.prop(scene, "qmc_origin_mode", text="Set Origin")

        # --- Advanced ---
        if section_header(layout, scene, "qmc_ui_show_advanced", "Advanced"):
            col = layout.box().column(align=True)
            col.label(text="Apply before cleanup:")
            row = col.row(align=True)
            row.prop(scene, "qmc_apply_loc", text="Loc", toggle=True)
            row.prop(scene, "qmc_apply_rot", text="Rot", toggle=True)
            row.prop(scene, "qmc_apply_scale", text="Scale", toggle=True)
            col.prop(scene, "qmc_apply_modifiers")
            col.prop(scene, "qmc_decimate_ratio")
            col.separator()
            col.prop(scene, "qmc_make_single_user")
            col.prop(scene, "qmc_remove_unused_materials")
            col.prop(scene, "qmc_remove_empty_vgroups")
            col.prop(scene, "qmc_rename_data")
            col.prop(scene, "qmc_view_selected")

        # --- Scene Data ---
        if section_header(layout, scene, "qmc_ui_show_data", "Scene Data"):
            box = layout.box()
            col = box.column(align=True)
            col.operator("mesh.qmc_purge_unused", icon='TRASH')
            col.separator()
            col.prop(scene, "qmc_unpack_method", text="Unpack")
            row = col.row(align=True)
            row.operator("mesh.qmc_pack_resources", text="Pack", icon='PACKAGE')
            row.operator("mesh.qmc_unpack_resources", text="Unpack", icon='UGLYPACKAGE')
            col.separator()
            col.label(text=f"Packed images: {sum(1 for i in bpy.data.images if i.packed_file)}")

        layout.separator()
        row = layout.row(align=True)
        row.scale_y = 1.4
        row.operator("mesh.quick_cleanup_all_in_one", icon='CHECKMARK')
        row = layout.row(align=True)
        row.operator("mesh.qmc_analyze", icon='ZOOM_ALL')
        row.operator("mesh.qmc_dump_log", text="", icon='TEXT')

        if scene.qmc_last_report:
            box = layout.box()
            box.label(text="Last run:", icon='INFO')
            col = box.column(align=True)
            for chunk in scene.qmc_last_report.split(" | "):
                col.label(text=chunk)

        layout.label(text="Shortcut: Ctrl + Alt + Q")


# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------

class QMC_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__

    debug_logging: bpy.props.BoolProperty(
        name="Debug Logging",
        default=False,
        description="Record a detailed log and print it to the system console. "
                    "Leave this off for best performance on large scenes")

    # Custom preset slot - persists across .blend files.
    custom_scope: bpy.props.EnumProperty(items=QMC_SCOPE_ITEMS, default='SELECTED')
    custom_select_all: bpy.props.BoolProperty(default=True)
    custom_merge_vertices: bpy.props.BoolProperty(default=True)
    custom_merge_distance: bpy.props.FloatProperty(default=0.0001)
    custom_dissolve_degenerate: bpy.props.BoolProperty(default=False)
    custom_degenerate_distance: bpy.props.FloatProperty(default=0.0001)
    custom_dissolve_limited: bpy.props.BoolProperty(default=False)
    custom_dissolve_angle: bpy.props.FloatProperty(default=5.0)
    custom_dissolve_delimit: bpy.props.EnumProperty(
        items=QMC_DELIMIT_ITEMS, default={'NORMAL'}, options={'ENUM_FLAG'})
    custom_tris_to_quads: bpy.props.BoolProperty(default=False)
    custom_tris_to_quads_angle: bpy.props.FloatProperty(default=0.698132)
    custom_tris_to_quads_compare: bpy.props.EnumProperty(
        items=QMC_COMPARE_ITEMS, default={'SEAM', 'SHARP'}, options={'ENUM_FLAG'})
    custom_triangulate: bpy.props.BoolProperty(default=False)
    custom_delete_loose: bpy.props.BoolProperty(default=True)
    custom_fill_holes: bpy.props.BoolProperty(default=False)
    custom_fill_holes_sides: bpy.props.IntProperty(default=4)
    custom_fix_non_manifold: bpy.props.BoolProperty(default=False)
    custom_recalc_normals: bpy.props.BoolProperty(default=True)
    custom_recalc_inside: bpy.props.BoolProperty(default=False)
    custom_reset_vectors: bpy.props.BoolProperty(default=False)
    custom_clear_split_normals: bpy.props.BoolProperty(default=False)
    custom_clear_sharp: bpy.props.BoolProperty(default=False)
    custom_clear_seams: bpy.props.BoolProperty(default=False)
    custom_origin_mode: bpy.props.EnumProperty(items=QMC_ORIGIN_MODE_ITEMS, default='NONE')
    custom_shade_mode: bpy.props.EnumProperty(items=QMC_SHADE_MODE_ITEMS, default='NONE')
    custom_auto_smooth_angle: bpy.props.FloatProperty(default=0.523599)
    custom_apply_loc: bpy.props.BoolProperty(default=False)
    custom_apply_rot: bpy.props.BoolProperty(default=False)
    custom_apply_scale: bpy.props.BoolProperty(default=False)
    custom_apply_modifiers: bpy.props.BoolProperty(default=False)
    custom_decimate_ratio: bpy.props.FloatProperty(default=1.0)
    custom_make_single_user: bpy.props.BoolProperty(default=True)
    custom_remove_unused_materials: bpy.props.BoolProperty(default=False)
    custom_remove_empty_vgroups: bpy.props.BoolProperty(default=False)
    custom_rename_data: bpy.props.BoolProperty(default=False)
    custom_view_selected: bpy.props.BoolProperty(default=False)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "debug_logging")
        layout.label(text="The Custom preset slot is stored here and persists across .blend files.")
        layout.label(text="Save it from the sidebar: Quick Cleanup+ > Custom > Save.")


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def scene_prop_defs():
    P = bpy.props
    return {
        # UI state
        "qmc_ui_show_topology": P.BoolProperty(name="Topology", default=True),
        "qmc_ui_show_normals": P.BoolProperty(name="Normals / Data", default=True),
        "qmc_ui_show_shading": P.BoolProperty(name="Shading / Origin", default=True),
        "qmc_ui_show_advanced": P.BoolProperty(name="Advanced", default=False),
        "qmc_ui_show_data": P.BoolProperty(name="Scene Data", default=False),
        "qmc_last_report": P.StringProperty(name="Last Report", default=""),

        # Scope
        "qmc_scope": P.EnumProperty(
            name="Scope", items=QMC_SCOPE_ITEMS, default='SELECTED',
            description="Which mesh objects the cleanup runs on"),

        # Topology
        "qmc_select_all": P.BoolProperty(
            name="Whole Mesh", default=True,
            description="Process every element. Turn this off to only clean up the geometry "
                        "that is currently selected in the mesh"),
        "qmc_merge_vertices": P.BoolProperty(
            name="Merge by Distance", default=True,
            description="Merge vertices that are closer together than the merge distance"),
        "qmc_merge_distance": P.FloatProperty(
            name="Merge Distance", default=0.0001, min=0.0, step=0.001, precision=6,
            description="Distance threshold for merging vertices, in Blender units"),
        "qmc_dissolve_degenerate": P.BoolProperty(
            name="Dissolve Degenerate", default=False,
            description="Collapse zero-length edges and zero-area faces"),
        "qmc_degenerate_distance": P.FloatProperty(
            name="Degenerate Distance", default=0.0001, min=0.0, step=0.001, precision=6,
            description="Size below which edges and faces count as degenerate"),
        "qmc_delete_loose": P.BoolProperty(
            name="Delete Loose", default=True,
            description="Remove wire edges and stray vertices that are not part of any face"),
        "qmc_fix_non_manifold": P.BoolProperty(
            name="Fix Non-Manifold", default=False,
            description="Delete edges shared by three or more faces. Open boundaries are left alone"),
        "qmc_fill_holes": P.BoolProperty(
            name="Fill Holes", default=False,
            description="Close boundary loops with new faces"),
        "qmc_fill_holes_sides": P.IntProperty(
            name="Max Sides", default=4, min=0, max=1000,
            description="Only fill holes with at most this many sides. 0 fills any hole"),
        "qmc_dissolve_limited": P.BoolProperty(
            name="Limited Dissolve", default=False,
            description="Merge coplanar faces within the angle limit"),
        "qmc_dissolve_angle": P.FloatProperty(
            name="Angle Limit", default=5.0, min=0.0, max=180.0,
            description="Maximum angle between faces to dissolve, in degrees"),
        "qmc_dissolve_delimit": P.EnumProperty(
            name="Delimit", items=QMC_DELIMIT_ITEMS, default={'NORMAL'}, options={'ENUM_FLAG'},
            description="Boundaries the dissolve must not cross. Without these, UVs and "
                        "material assignments get destroyed"),
        "qmc_tris_to_quads": P.BoolProperty(
            name="Tris to Quads", default=False,
            description="Join adjacent triangles back into quads"),
        "qmc_tris_to_quads_angle": P.FloatProperty(
            name="Max Angle", default=0.698132, min=0.0, max=math.pi,
            subtype='ANGLE',
            description="Maximum face and shape angle for joining triangles"),
        "qmc_tris_to_quads_compare": P.EnumProperty(
            name="Preserve", items=QMC_COMPARE_ITEMS, default={'SEAM', 'SHARP'},
            options={'ENUM_FLAG'},
            description="Attributes that block a join, so they survive the conversion"),
        "qmc_triangulate": P.BoolProperty(
            name="Triangulate", default=False,
            description="Triangulate the whole mesh at the end. Useful for game engine export"),

        # Normals
        "qmc_recalc_normals": P.BoolProperty(
            name="Recalculate Normals", default=True,
            description="Make face normals consistent and outward-facing"),
        "qmc_recalc_inside": P.BoolProperty(
            name="Recalculate Inside", default=False,
            description="Flip normals to face inward after recalculating"),
        "qmc_clear_split_normals": P.BoolProperty(
            name="Clear Custom Split Normals", default=False,
            description="Remove custom split normal data so normals fall back to the computed ones"),
        "qmc_reset_vectors": P.BoolProperty(
            name="Reset Vectors", default=False,
            description="Reset custom normals to their default values. Same end result as "
                        "clearing custom split normals"),
        "qmc_clear_sharp": P.BoolProperty(
            name="Clear Sharp Edges", default=False,
            description="Remove all sharp edge markings"),
        "qmc_clear_seams": P.BoolProperty(
            name="Clear UV Seams", default=False,
            description="Remove all UV seam markings"),

        # Shading / origin
        "qmc_shade_mode": P.EnumProperty(
            name="Shade Mode", items=QMC_SHADE_MODE_ITEMS, default='NONE',
            description="Shading to set after cleanup"),
        "qmc_auto_smooth_angle": P.FloatProperty(
            name="Auto Smooth Angle", default=0.523599, min=0.0, max=math.pi,
            subtype='ANGLE',
            description="Angle above which edges stay sharp when using Auto Smooth"),
        "qmc_origin_mode": P.EnumProperty(
            name="Set Origin", items=QMC_ORIGIN_MODE_ITEMS, default='NONE',
            description="Origin handling after cleanup"),

        # Advanced
        "qmc_apply_loc": P.BoolProperty(name="Apply Location", default=False),
        "qmc_apply_rot": P.BoolProperty(name="Apply Rotation", default=False),
        "qmc_apply_scale": P.BoolProperty(name="Apply Scale", default=False),
        "qmc_apply_modifiers": P.BoolProperty(
            name="Apply Modifiers", default=False,
            description="Apply the whole modifier stack before cleaning up. "
                        "Objects with shape keys are skipped"),
        "qmc_decimate_ratio": P.FloatProperty(
            name="Decimate Ratio", default=1.0, min=0.0, max=1.0,
            description="Below 1.0, collapse-decimate to this ratio before cleanup"),
        "qmc_make_single_user": P.BoolProperty(
            name="Make Single User", default=True,
            description="Copy mesh data shared between objects first. Turn this off to clean "
                        "linked duplicates once instead of copying them"),
        "qmc_remove_unused_materials": P.BoolProperty(
            name="Remove Unused Material Slots", default=False,
            description="Drop material slots that no face uses"),
        "qmc_remove_empty_vgroups": P.BoolProperty(
            name="Remove Empty Vertex Groups", default=False,
            description="Drop vertex groups with no weighted vertices. Costs an extra scan "
                        "over every vertex"),
        "qmc_rename_data": P.BoolProperty(
            name="Rename Mesh Data to Object", default=False,
            description="Rename each mesh data-block to match its object"),
        "qmc_view_selected": P.BoolProperty(
            name="Frame After Cleanup", default=False,
            description="Frame the cleaned objects in the 3D View when finished"),

        # Scene data
        "qmc_unpack_method": P.EnumProperty(
            name="Unpack Method", items=QMC_UNPACK_METHOD_ITEMS, default='USE_LOCAL',
            description="Default method for unpacking resources"),
    }


classes = (
    QMC_AddonPreferences,
    MESH_OT_qmc_preset,
    MESH_OT_qmc_save_custom_preset,
    MESH_OT_qmc_analyze,
    MESH_OT_qmc_purge_unused,
    MESH_OT_qmc_pack_resources,
    MESH_OT_qmc_unpack_resources,
    MESH_OT_qmc_dump_log,
    MESH_OT_quick_cleanup_all_in_one,
    VIEW3D_PT_quick_cleanup_panel,
)

_registered_scene_props = []


def register_keymap():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if not kc:
        return
    try:
        km = kc.keymaps.new(name='3D View', space_type='VIEW_3D')
        kmi = km.keymap_items.new("mesh.quick_cleanup_all_in_one", 'Q', 'PRESS', ctrl=True, alt=True)
        addon_keymaps.append((km, kmi))
    except Exception as e:
        warn(f"keymap registration failed: {e}")


def unregister_keymap():
    for km, kmi in addon_keymaps:
        try:
            km.keymap_items.remove(kmi)
        except Exception:
            pass
    addon_keymaps.clear()


def register():
    for c in classes:
        bpy.utils.register_class(c)

    # Registering and unregistering from the same source means the two lists
    # can no longer drift apart and leak properties on reload.
    for name, prop in scene_prop_defs().items():
        setattr(bpy.types.Scene, name, prop)
        _registered_scene_props.append(name)

    register_keymap()


def unregister():
    unregister_keymap()

    for name in _registered_scene_props:
        if hasattr(bpy.types.Scene, name):
            try:
                delattr(bpy.types.Scene, name)
            except Exception:
                pass
    _registered_scene_props.clear()

    for c in reversed(classes):
        try:
            bpy.utils.unregister_class(c)
        except Exception:
            pass


if __name__ == "__main__":
    register()
