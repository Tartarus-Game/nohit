extends Node
var stage
var soul
var tick = 0
var active = false
var done = false
var damage_calls = 0
var observed = {}
var route = []
var states = []
var replay = []
var output = "user://nohit-undotale.json"
var strategy = 0
var spawn_count = 0
var component = false
func _ready():
 pause_mode = Node.PAUSE_MODE_PROCESS
 for arg in OS.get_cmdline_args():
  if arg.begins_with("--out="): output = arg.substr(6)
  if arg=="--component":component=true
  if arg.begins_with("--strategy="): strategy = int(arg.substr(11))
  if arg.begins_with("--replay="):
   var f = File.new()
   f.open(arg.substr(9),File.READ)
   replay = JSON.parse(f.get_as_text()).result.route
 seed(1)
 call_deferred("setup")
func setup():
 stage = load("res://BattleEngine/BattleEngine.tscn").instance()
 add_child(stage)
 soul = stage.soul
 stage.buttons.enable = false
 stage.box.resize(Vector2(300,140),null,1,1,1.5)
 yield(get_tree().create_timer(2),"timeout")
 soul.global_position = stage.box.rect_global_position + stage.box.rect_size/2
 stage.enemies.soul = soul
 stage.enemies.box = stage.box
 stage.enemies.connect("cutscene_end",self,"on_done")
 if component:
  soul.changeMovement("red")
  soul.changeMovement("blue")
  spawn_component()
 else:
  stage.enemies.attack()
 active = true
 print("NOHIT_NATIVE_BEGIN")
func on_done(): done = true
func on_damage(): damage_calls += 1
func gather(n):
 if n.get_script() and n.get_script().resource_path.ends_with("/Bone.gd"): observed[n.get_instance_id()] = true
 for c in n.get_children():gather(c)
func _physics_process(_delta):
 if not active:return
 if tick > 0:
  states.append({"tick":tick,"x":soul.global_position.x,"y":soul.global_position.y,"vx":soul.motion.x,"vy":soul.motion.y,"hp":soul.health,"mode":soul.currentFunction})
 gather(stage)
 if damage_calls > 0:
  finish("hit")
  return
 if component and tick>=400:
  done=observed.size()==3
  for b in stage.box.attacks.get_children():
   if b.global_position.x <= stage.box.rect_global_position.x+stage.box.rect_size.x+30:done=false
 if done:
  finish("native_nohit" if soul.health==48 and observed.size()==(3 if component else 11) else "unknown")
  return
 if tick >= 1500:
  finish("unknown")
  return
 var mask = 0
 if not replay.empty():
  if tick>=replay.size():
   finish("replay_length_mismatch")
   return
  mask = int(replay[tick])
 else:
  if strategy < 16:mask = strategy
  else:
   var phase = int(tick/15)%4
   mask = [4,0,4,0][phase] if strategy==16 else [5,4,6,4][phase]
 var names = ["ui_left","ui_right","ui_up","ui_down"]
 for i in range(4):
  if mask & (1<<i):Input.action_press(names[i])
  else:Input.action_release(names[i])
 route.append(mask)
 tick += 1
func finish(status):
 active = false
 var f = File.new();f.open(output,File.WRITE)
 f.store_string(JSON.print({"status":status,"component":component,"ticks":tick,"route":route,"states":states,"damage_calls":damage_calls,"hp":soul.health,"attack_completed":done,"observed_bullets":observed.size(),"strategy":strategy,"engine":Engine.get_version_info()}))
 print("NOHIT_NATIVE_END ",status," tick=",tick," damage=",damage_calls," spawned=",observed.size())
 get_tree().quit(0 if status=="native_nohit" else 2)

func spawn_component():
 for i in range(3):
  var bone=load("res://BattleEngine/Fight_Manager/Revenge Papyrus/Attacks/Bone.tscn").instance()
  bone.motion=Vector2(100,0)
  bone.switch_from("bot")
  stage.box.attacks.add_child(bone)
  bone.global_position=stage.box.rect_global_position+Vector2(-30,stage.box.rect_size.y-16)
  bone.visual.rect_size.y=30
  yield(get_tree().create_timer(1),"timeout")
