extends Node2D
## Standalone integration fixture, NOT an upstream attack or Undertale physics.
signal damaged(amount)
signal attack_finished
var running = false
var tick = 0
var hp = 20
var soul_position = Vector2(50, 50)
var soul_shape = CircleShape2D.new()
var bullet_shape = RectangleShape2D.new()

func _ready():
	soul_shape.radius = 3
	bullet_shape.size = Vector2(8, 28)

func start_attack(_seed):
	running = true

func _physics_process(_delta):
	if not running: return
	# Existing InputMap movement stays in the game; adapter only injects actions.
	var movement = Vector2(int(Input.is_action_pressed("ui_right")) - int(Input.is_action_pressed("ui_left")),
		int(Input.is_action_pressed("ui_down")) - int(Input.is_action_pressed("ui_up")))
	soul_position += movement * 2
	soul_position = soul_position.clamp(Vector2(5, 5), Vector2(95, 95))
	tick += 1
	var bullet_position = Vector2(110 - tick * 2, 50)
	if soul_shape.collide(Transform2D(0, soul_position), bullet_shape, Transform2D(0, bullet_position)):
		hp -= 1
		damaged.emit(1)
	if tick == 45:
		running = false
		attack_finished.emit()
