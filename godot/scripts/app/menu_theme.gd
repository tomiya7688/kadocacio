class_name MenuTheme
extends RefCounted
## Shared colors and visible focus styles for native Control widgets.


static func build() -> Theme:
	var theme: Theme = Theme.new()
	theme.default_font_size = 20
	for type: String in ["Button", "OptionButton", "LineEdit", "ItemList", "RichTextLabel", "Label", "CheckButton"]:
		theme.set_color("font_color", type, Color("edf4f2"))
	for type: String in ["Button", "OptionButton", "LineEdit", "ItemList"]:
		theme.set_stylebox("normal" if type in ["Button", "OptionButton", "LineEdit"] else "panel", type, _box(Color("152c31"), Color("3e6269")))
		theme.set_stylebox("focus", type, _box(Color(0, 0, 0, 0), Color("ffd18b"), 3))
	for type: String in ["Button", "OptionButton"]:
		theme.set_stylebox("hover", type, _box(Color("21464a"), Color("75c6b0")))
		theme.set_stylebox("pressed", type, _box(Color("326558"), Color("75c6b0")))
		theme.set_stylebox("disabled", type, _box(Color("15232a"), Color("31434a")))
	return theme


static func _box(color: Color, border: Color, width: int = 1) -> StyleBoxFlat:
	var box: StyleBoxFlat = StyleBoxFlat.new()
	box.bg_color = color
	box.border_color = border
	box.set_border_width_all(width)
	box.set_corner_radius_all(10)
	box.content_margin_left = 14
	box.content_margin_right = 14
	box.content_margin_top = 8
	box.content_margin_bottom = 8
	return box
