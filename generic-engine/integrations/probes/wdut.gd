extends Node
var tick = 0
var stage
var max_nodes = 0
var max_collisions = 0
var node_paths = {}
func _ready():
 var scene = load("uid://b72rkv2gjlqgd")
 if not scene:
  print("NOHIT_PROBE_LOAD_FAILED")
  get_tree().quit(3)
  return
 stage = scene.instantiate()
 add_child(stage)
 print("NOHIT_PROBE_LOADED")
func visit(n):
 var count = 1
 if n is CollisionObject2D: max_collisions += 1
 if n.get_script(): node_paths[str(n.get_path())] = str(n.get_script().resource_path)
 for c in n.get_children(): count += visit(c)
 return count
func _physics_process(_delta):
 tick += 1
 if tick == 120:
  get_node("/root/scene_changer").load_battle(load("res://Battle/tres/sans_cpp.tres"),false,Vector2(48,452))
 if tick == 240:
  var battles=get_tree().root.find_children("*","BattleMain",true,false)
  if not battles.is_empty():
   var b=battles[0]
   b._on_enemy_turn_start()
   b.get_node("Attacks/BoxClipper").add_attack(load("res://Battle/attacks/attack_sans_gd.tscn"))
   b.get_node("Attacks/BoxClipper").start_attacks()
   print("WDUT_NATIVE_ATTACK_STARTED")
 if tick % 60 == 0:
  max_collisions = 0
  max_nodes = max(max_nodes,visit(get_tree().root))
 for name in ["ui_accept","ui_cancel","confirm","accept","z","enter"]:
  if InputMap.has_action(name):
   if tick % 90 == 1: Input.action_press(name)
   else: Input.action_release(name)
 if tick >= 1200:
  print("NOHIT_PROBE_FINISHED ", tick, " nodes=",max_nodes," collision_objects=",max_collisions)
  print("NOHIT_PROBE_SCRIPTS ", node_paths)
  get_tree().quit()
