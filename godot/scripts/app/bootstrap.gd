class_name KadocalcioBootstrap
extends Control
## Presentation-only migration entry. No simulation or team/save I/O belongs here.


func _ready() -> void:
	var exit_button: Button = %Exit
	exit_button.pressed.connect(_request_exit)
	exit_button.grab_focus()
	print("KADOCALCIO_BOOTSTRAP_READY")
	if OS.get_cmdline_user_args().has("--smoke-exit"):
		_request_exit.call_deferred()


func _request_exit() -> void:
	print("KADOCALCIO_BOOTSTRAP_STOP")
	get_tree().quit(0)
