import re
import bpy

from .BlenderObjects import apply_modifiers
from .Functions import (
    debug,
    deselect_all_objects,
    get_global_props,
    get_path_filename,
    is_obj_visible_by_name,
    radians,
    radian_list,
    set_active_object,
    fix_slash,
    load_image_into_blender,
    get_addon_assets_path,
    show_report_popup,
)
from .Constants import SPECIAL_NAME_PREFIX_ICON_ONLY


def _get_cam_position() -> list:
    """return roation_euler list for the icon_obj"""
    tm_props = get_global_props()
    style = tm_props.LI_icon_perspective
    if style == "CLASSIC_SE":
        return radian_list(55, 0, 45)
    if style == "CLASSIC_SW":
        return radian_list(55, 0, 135)
    if style == "CLASSIC_NW":
        return radian_list(55, 0, 225)
    if style == "CLASSIC_NE":
        return radian_list(55, 0, 315)
    if style == "TOP":
        return radian_list(0, 0, 0)
    if style == "LEFT":
        return radian_list(90, 0, -90)
    if style == "RIGHT":
        return radian_list(90, 0, 90)
    if style == "BACK":
        return radian_list(90, 0, 180)
    if style == "FRONT":
        return radian_list(90, 0, 0)
    if style == "BOTTOM":
        return radian_list(180, 0, 0)


def _make_joined_object(objects: list[bpy.types.Object]) -> bpy.types.Object:
    # Ensure the context is set correctly
    bpy.ops.object.mode_set(mode='OBJECT')  # Ensure we are in OBJECT mode

    deselect_all_objects()

    for obj in objects:
        if (
            obj.type == "MESH"
            and (
                is_obj_visible_by_name(obj.name)
                or obj.name.startswith(SPECIAL_NAME_PREFIX_ICON_ONLY)
            )
            and not "lod1" in obj.name.lower()
        ):
            obj.select_set(True)  # Select the object

    # Ensure at least one object is selected
    if not bpy.context.selected_objects:
        raise RuntimeError("No valid objects to join")

    bpy.context.view_layer.objects.active = bpy.context.selected_objects[0]  # Set the active object

    # Duplicate objects to avoid modifying original ones
    bpy.ops.object.duplicate(linked=False)

    for obj in bpy.context.selected_objects:
        apply_modifiers(obj)

    # Join selected objects
    try:
        bpy.ops.object.join()
    except RuntimeError as e:
        raise RuntimeError(f"Failed to join objects: {e}")

    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    joined_obj = bpy.context.object

    joined_obj.name = "JOINED_OBJECT_FOR_ICON"
    joined_obj.hide_render = False

    bpy.ops.object.transform_apply(location=False, scale=True, rotation=True)

    bpy.context.scene.collection.objects.link(joined_obj)

    return joined_obj



def _make_empty_object(location: list[float]) -> bpy.types.Object:
    empty = bpy.data.objects.new(
        "EMPTY_ANCHOR_FOR_ICON", None
    )  # Create new empty object
    empty.empty_display_type = "CUBE"
    empty.location = location.copy()

    bpy.context.scene.collection.objects.link(empty)

    return empty


def _add_icon_view_layer_and_set_active() -> bpy.types.ViewLayer:
    ICON_VW_NAME = "ICON_VIEW_LAYER"
    icon_view_layer = bpy.context.scene.view_layers.get(ICON_VW_NAME, None)

    if not icon_view_layer:
        bpy.ops.scene.view_layer_add(type="NEW")
        icon_view_layer = bpy.context.window.view_layer
        icon_view_layer.name = ICON_VW_NAME

    bpy.context.window.view_layer = icon_view_layer
    for vl_col in bpy.context.scene.view_layers[ICON_VW_NAME].layer_collection.children:
        vl_col.exclude = True

    return icon_view_layer


def _add_camera(empty: bpy.types.Object) -> bpy.types.Camera:

    bpy.ops.object.camera_add(location=(0, 0, 0), rotation=(0, 0, 0))

    icon_cam = bpy.context.object
    icon_cam.name = "ICON_CAMERA"

    icon_cam.data.type = "ORTHO"
    icon_cam.data.show_limits = False
    icon_cam.data.clip_end = 10_000
    bpy.context.scene.camera = icon_cam

    icon_cam.parent = empty

    return icon_cam


def generate_collection_icon(coll: bpy.types.Collection, export_path: str = None):
    generate_objects_icon(coll.objects, coll.name, export_path)


def generate_objects_icon(
    objects: list[bpy.types.Object], name: str, export_path: str = None
):
    tm_props = get_global_props()
    overwrite_icon = tm_props.CB_icon_overwriteIcons
    icon_name = get_path_filename(export_path) if export_path is not None else name
    icon_size = tm_props.NU_icon_padding / 100
    current_view_layer = bpy.context.window.view_layer
    current_selection = bpy.context.selected_objects.copy()

    if not overwrite_icon:
        debug(f"icon creation canceled, <{ icon_name }> already exists")
        return

    debug(f"creating icon <{icon_name}>")

    is_single_object = len(objects) == 1

    joined_obj = _make_joined_object(objects) if not is_single_object else objects[0]

    joined_obj.hide_render = False

    vl = _add_icon_view_layer_and_set_active()

    # objects in root collection "Scene Collection" need to stay linked/relinked after icon creation
    # other objects/collections can be unlinked
    root_coll_objs = []

    for obj in objects:
        try:
            vl.active_layer_collection.collection.objects.link(obj)
        except RuntimeError as e:
            root_coll_objs.append(obj)

    # HIDE ALL BUT JOINED
    for obj in bpy.context.scene.collection.objects:
        if obj.name != joined_obj.name:
            obj.hide_render = True

    # EMPTY
    empty = _make_empty_object(joined_obj.location.copy())

    # CAM------------------
    camera = _add_camera(empty)

    style = _get_cam_position()
    empty.rotation_euler = style

    deselect_all_objects()

    try:
        joined_obj.select_set(True)
        bpy.context.scene.camera = camera
        bpy.ops.view3d.camera_to_view_selected()
        camera.data.ortho_scale = camera.data.ortho_scale / icon_size
        deselect_all_objects()

    except Exception as e:
        show_report_popup(
            "ERROR, no icon generated: Icon camera is None, please make bugreport and provide your blendfile."
        )
        print(e)

    # RENDER----------------------
    bpy.context.scene.render.image_settings.file_format = "PNG"
    bpy.context.scene.render.filepath = export_path if export_path is not None else ""
    bpy.context.scene.render.use_single_layer = True
    bpy.context.scene.render.resolution_x = (
        int(tm_props.LI_icon_pxDimension) # MP & TM are are always 64px
    )
    bpy.context.scene.render.resolution_y = (
        int(tm_props.LI_icon_pxDimension) # MP & TM are are always 64px
    )
    bpy.context.scene.eevee.taa_render_samples = 16

    generate_world_node()

    bpy.ops.render.render(write_still=export_path is not None)

    # CLEAN UP -----------------
    # CLEAN UP -----------------
    # CLEAN UP -----------------
    # CLEAN UP -----------------

    # remove icon dummy if it was generated from a collection
    # single item with _item_ prefix needs to stay
    if not is_single_object:
        bpy.data.objects.remove(joined_obj, do_unlink=True)

    for obj in objects:
        coll = vl.active_layer_collection.collection
        coll.objects.unlink(obj)

    for obj in root_coll_objs:
        coll = vl.active_layer_collection.collection
        try:  # object could have been removed
            coll.objects.link(obj)
        except ReferenceError:
            pass  # ReferenceError: StructRNA of type Object has been removed

    bpy.context.window.view_layer = current_view_layer

    bpy.data.objects.remove(camera, do_unlink=True)
    bpy.data.objects.remove(empty, do_unlink=True)
    for obj in current_selection:
        print(obj)
        try:
            set_active_object(obj)
        except:
            pass

    debug(f"created icon <{icon_name}>")

    # show render window (test render button clicked)
    if export_path is None:
        bpy.ops.render.view_show("INVOKE_DEFAULT")


def generate_world_node():
    tm_props = get_global_props()
    worlds = bpy.data.worlds
    tm_world = "tm_icon_world"
    scene = bpy.context.scene

    if not tm_world in worlds:
        worlds.new(tm_world)

    tm_world = worlds[tm_world]
    tm_world.use_nodes = True

    scene.world = tm_world

    if tm_props.LI_icon_world == "STANDARD":
        _generate_standartd_world_node(tm_world)
    else:
        _generate_trackmania_world_nodes(
            tm_world, tm_props.LI_icon_world.split("-")[-1].lower()
        )


def _generate_standartd_world_node(world: bpy.types.World):
    white = (1, 1, 1, 1)
    nodes = world.node_tree.nodes
    links = world.node_tree.links

    rgb_node = "TM_RGB"
    bg_node = "TM_BACKGROUND"
    output_node = "TM_OUTPUT"
    mix_node = "TM_MIX_SHADER"
    camera_node = "TM_LIGHT_NODE"

    # walrus here? print(a) //ref err ... print(a:=5) //5 ... print(a) //5
    # blender >=2.93 with python 3.9
    reqNodes = [rgb_node, bg_node, output_node, mix_node, camera_node]

    allFine = True

    for required_node in reqNodes:
        if required_node not in nodes:

            allFine = False
            debug("generate world node, atleast one was missing")
            for node in nodes:
                nodes.remove(node)  # clear all

            nodes.new("ShaderNodeRGB").name = rgb_node
            nodes.new("ShaderNodeBackground").name = bg_node
            nodes.new("ShaderNodeOutputWorld").name = output_node
            nodes.new("ShaderNodeMixShader").name = mix_node
            nodes.new("ShaderNodeLightPath").name = camera_node
            break

    if allFine:
        return

    xy = lambda x, y: ((150 * x), -(200 * y))

    camera_node = nodes[camera_node]
    camera_node.location = xy(0, 0)

    rgb_node = nodes[rgb_node]
    rgb_node.outputs[0].default_value = white
    rgb_node.location = xy(0, 2)

    bg_node = nodes[bg_node]
    bg_node.location = xy(0, 3)

    mix_node = nodes[mix_node]
    mix_node.location = xy(2, 2)

    output_node = nodes[output_node]
    output_node.location = xy(4, 2)

    links.new(camera_node.outputs[0], mix_node.inputs[0])
    links.new(rgb_node.outputs[0], mix_node.inputs[1])
    links.new(bg_node.outputs[0], mix_node.inputs[2])
    links.new(mix_node.outputs[0], output_node.inputs[0])


def _generate_trackmania_world_nodes(world: bpy.types.World, daytime: str = "day"):
    nodes = world.node_tree.nodes
    links = world.node_tree.links

    for node in nodes:
        nodes.remove(node)

    # nodes
    texCoords: bpy.types.ShaderNodeTexCoord = _get_or_create_node(
        nodes, "TM_TEXCOORD", "ShaderNodeTexCoord", (0, 0)
    )

    lightVectorMath: bpy.types.ShaderNodeMapping = _get_or_create_node(
        nodes, "TM_LIGHT_VM", "ShaderNodeMapping", (1, 0)
    )
    lightVectorMath.vector_type = "POINT"

    grad: bpy.types.ShaderNodeTexGradient = _get_or_create_node(
        nodes, "TM_GRADIENT", "ShaderNodeTexGradient", (2, 0)
    )

    ceil: bpy.types.ShaderNodeMath = _get_or_create_node(
        nodes, "TM_CEILT", "ShaderNodeMath", (3, 0)
    )
    ceil.operation = "CEIL"
    blackBody: bpy.types.ShaderNodeBlackbody = _get_or_create_node(
        nodes, "TM_BLACK_BODY", "ShaderNodeBlackbody", (3, -1)
    )

    mixRGB: bpy.types.ShaderNodeMix = _get_or_create_node(
        nodes, "TM_MIX_RGB", "ShaderNodeMix", (4, 0)
    )
    mixRGB.data_type = "RGBA"
    mixRGB.inputs["A"].default_value = (0.0, 0.0, 0.0, 1.0)

    emmision: bpy.types.ShaderNodeEmission = _get_or_create_node(
        nodes, "TM_EMMISION", "ShaderNodeEmission", (5, 0)
    )

    hdriVectorMath: bpy.types.ShaderNodeMapping = _get_or_create_node(
        nodes, "TM_HDRI_VM", "ShaderNodeMapping", (1, 3)
    )
    hdriVectorMath.vector_type = "POINT"

    image: bpy.types.ShaderNodeTexEnvironment = _get_or_create_node(
        nodes, "TM_IMAGE", "ShaderNodeTexEnvironment", (2, 3)
    )

    lightPath: bpy.types.ShaderNodeLightPath = _get_or_create_node(
        nodes, "TM_LIGHT_PATH", "ShaderNodeLightPath", (6, 0)
    )
    mixShader: bpy.types.ShaderNodeMixShader = _get_or_create_node(
        nodes, "TM_MIX_SHADER", "ShaderNodeMixShader", (6, 1)
    )
    addShader: bpy.types.ShaderNodeAddShader = _get_or_create_node(
        nodes, "TM_ADD_SHADER", "ShaderNodeAddShader", (6, 2)
    )

    lastMixShader: bpy.types.ShaderNodeMixShader = _get_or_create_node(
        nodes, "TM_LAST_MIX_SHADER", "ShaderNodeMixShader", (7, 1)
    )

    output: bpy.types.ShaderNodeOutputWorld = _get_or_create_node(
        nodes, "TM_OUTPUT", "ShaderNodeOutputWorld", (8, 1)
    )

    # links
    links.new(texCoords.outputs[0], lightVectorMath.inputs[0])
    links.new(texCoords.outputs[0], hdriVectorMath.inputs[0])

    links.new(lightVectorMath.outputs[0], grad.inputs[0])
    links.new(hdriVectorMath.outputs[0], image.inputs[0])

    links.new(grad.outputs[1], ceil.inputs[0])

    links.new(ceil.outputs[0], mixRGB.inputs[0])
    links.new(blackBody.outputs[0], mixRGB.inputs["B"])

    links.new(mixRGB.outputs["Result"], emmision.inputs[0])

    links.new(emmision.outputs[0], addShader.inputs[0])
    links.new(emmision.outputs[0], mixShader.inputs[1])
    links.new(image.outputs[0], addShader.inputs[1])
    links.new(image.outputs[0], mixShader.inputs[2])

    links.new(lightPath.outputs[0], lastMixShader.inputs[0])
    links.new(addShader.outputs[0], lastMixShader.inputs[1])
    links.new(mixShader.outputs[0], lastMixShader.inputs[2])

    links.new(lastMixShader.outputs[0], output.inputs[0])

    # settings
    hdri_name = "Day.dds"
    if daytime == "night":
        lightVectorMath.inputs[1].default_value = (-0.999, 0, 0)
        lightVectorMath.inputs[2].default_value = (radians(25), 0, radians(135))
        hdriVectorMath.inputs[2].default_value = (0, 0, radians(135))
        blackBody.inputs[0].default_value = 6000
        emmision.inputs[1].default_value = 50
        mixShader.inputs[0].default_value = 0.995
        hdri_name = "Night.dds"
    elif daytime == "sunset":
        lightVectorMath.inputs[1].default_value = (-0.999, 0, 0)
        lightVectorMath.inputs[2].default_value = (radians(-15), 0, radians(260))
        hdriVectorMath.inputs[2].default_value = (0, 0, radians(260))
        blackBody.inputs[0].default_value = 3000
        emmision.inputs[1].default_value = 200
        mixShader.inputs[0].default_value = 0.995
        hdri_name = "Sunset.dds"
    elif daytime == "sunrise":
        lightVectorMath.inputs[1].default_value = (-0.999, 0, 0)
        lightVectorMath.inputs[2].default_value = (radians(15), 0, radians(110))
        hdriVectorMath.inputs[2].default_value = (0, 0, radians(110))
        blackBody.inputs[0].default_value = 4000
        emmision.inputs[1].default_value = 200
        mixShader.inputs[0].default_value = 0.995
        hdri_name = "Sunrise.dds"
    else:
        lightVectorMath.inputs[1].default_value = (-0.997, 0, 0)
        lightVectorMath.inputs[2].default_value = (radians(45), 0, radians(135))
        hdriVectorMath.inputs[2].default_value = (0, 0, radians(135))
        blackBody.inputs[0].default_value = 6000
        emmision.inputs[1].default_value = 200
        mixShader.inputs[0].default_value = 0.8

    success, name = load_image_into_blender(
        get_addon_assets_path() + "hdri/" + hdri_name
    )
    print(success, name)
    if success and name in bpy.data.images:
        image.image = bpy.data.images[name]


def _get_or_create_node(
    nodes: dict[str, bpy.types.Node],
    name: str,
    kind: str,
    location: list[float] = (0, 0),
) -> bpy.types.Node:
    if name in nodes:
        return nodes[name]

    node = nodes.new(kind)
    node.name = name
    node.location = (location[0] * 200, location[1] * 200)

    return node


def get_icon_path_from_fbx_path(filepath) -> str:
    icon_path = get_path_filename(filepath)
    icon_path = filepath.replace(icon_path, f"/Icon/{icon_path}")
    icon_path = re.sub("fbx", "tga", icon_path, re.IGNORECASE)
    return fix_slash(icon_path)
