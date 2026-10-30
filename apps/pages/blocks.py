from wagtail import blocks
from wagtail.images.blocks import ImageChooserBlock

RICH_FEATURES = ["h2", "h3", "bold", "italic", "ol", "ul", "link", "document-link", "hr"]


class ButtonBlock(blocks.StructBlock):
    label = blocks.CharBlock(label="tekst op de knop")
    page = blocks.PageChooserBlock(label="pagina", required=False)
    url = blocks.URLBlock(label="of externe link", required=False)

    class Meta:
        icon = "link"
        label = "Knop"
        template = "blocks/button.html"


class ImageBlock(blocks.StructBlock):
    image = ImageChooserBlock(label="foto")
    caption = blocks.CharBlock(label="onderschrift", required=False)

    class Meta:
        icon = "image"
        label = "Foto"
        template = "blocks/image.html"


class CalloutBlock(blocks.StructBlock):
    title = blocks.CharBlock(label="titel", required=False)
    text = blocks.RichTextBlock(label="tekst", features=RICH_FEATURES)

    class Meta:
        icon = "help"
        label = "Kader"
        template = "blocks/callout.html"


class CardBlock(blocks.StructBlock):
    title = blocks.CharBlock(label="titel")
    text = blocks.TextBlock(label="tekst")


class CardsBlock(blocks.StructBlock):
    cards = blocks.ListBlock(CardBlock(), label="kaarten")

    class Meta:
        icon = "table"
        label = "Kaarten naast elkaar"
        template = "blocks/cards.html"


class VideoBlock(blocks.StructBlock):
    url = blocks.URLBlock(label="YouTube-link")
    title = blocks.CharBlock(label="titel", required=False)

    class Meta:
        icon = "media"
        label = "YouTube-film"
        template = "blocks/video.html"


class BodyBlock(blocks.StreamBlock):
    heading = blocks.CharBlock(label="Tussentitel", icon="title", template="blocks/heading.html")
    paragraph = blocks.RichTextBlock(label="Tekst", features=RICH_FEATURES)
    image = ImageBlock()
    callout = CalloutBlock()
    cards = CardsBlock()
    button = ButtonBlock()
    video = VideoBlock()
