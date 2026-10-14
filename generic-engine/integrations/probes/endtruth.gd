extends Node
var tick = 0
var stage
var max_nodes = 0
var max_collisions = 0
var node_paths = {}
func _ready():
 var scene = load("res://bullet_hell_scene.tscn")
 if not scene:
  print("NOHIT_PROBE_LOAD_FAILED")
  get_tree().quit(3)
  return
 stage = scene.instantiate()
 add_child(stage)
 print("NOHIT_PROBE_LOADED")
 stage.start_battle({"soul_type":"determination","enemy_health":100,"patterns":["circle","spiral"],"start_with_enemy_turn":true})
func visit(n):
 var count = 1
 if n is CollisionObject2D: max_collisions += 1
 if n.get_script(): node_paths[str(n.get_path())] = str(n.get_script().resource_path)
 for c in n.get_children(): count += visit(c)
 return count
func _physics_process(_delta):
 tick += 1
 if tick == 120:stage.enemy.shoot_circle_pattern()
 if tick == 240:stage.enemy.shoot_spiral_pattern()
 if tick % 60 == 0:
  max_collisions = 0
  max_nodes = max(max_nodes,visit(get_tree().root))
 for name in []:
  if InputMap.has_action(name):
   if tick % 90 == 1: Input.action_press(name)
   else: Input.action_release(name)
 if tick >= 600:
  print("NOHIT_PROBE_FINISHED ", tick, " nodes=",max_nodes," collision_objects=",max_collisions)
  print("NOHIT_PROBE_SCRIPTS ", node_paths)
  get_tree().quit()
