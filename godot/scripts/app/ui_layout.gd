class_name UiLayout
extends RefCounted
## Small presentation-only factories; no application/data logic.


static func label(text: String, font_size: int = 20) -> Label:
	var node: Label = Label.new()
	node.text = text
	node.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	node.add_theme_font_size_override("font_size", font_size)
	node.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	return node


static func button(text: String) -> Button:
	var node: Button = Button.new()
	node.text = text
	node.custom_minimum_size.y = 48
	node.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	return node


static func page(parent: Control, heading: String) -> VBoxContainer:
	var margin: MarginContainer = MarginContainer.new()
	parent.add_child(margin)
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for side: String in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 30)
	var column: VBoxContainer = VBoxContainer.new()
	column.add_theme_constant_override("separation", 14)
	margin.add_child(column)
	column.add_child(label(heading, 32))
	return column


static func text_area(height: float) -> RichTextLabel:
	var node: RichTextLabel = RichTextLabel.new()
	node.custom_minimum_size.y = height
	node.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	node.size_flags_vertical = Control.SIZE_EXPAND_FILL
	node.selection_enabled = true
	node.bbcode_enabled = false
	return node
