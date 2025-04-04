import displayio

class SizedGroup(displayio.Group):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


    @property
    def size(self):
        min_x = 0
        min_y = 0
        max_x = 0
        max_y = 0

        for element in self:
            # print(type(element))
            if type(element) == displayio.TileGrid:
                if element.x < min_x:
                    min_x = element.x
                if element.y < min_y:
                    min_y = element.y

                _element_max_x = element.x + (element.width * element.tile_width)
                _element_max_y = element.y + (element.height * element.tile_height)
                if _element_max_x > max_x:
                    max_x = _element_max_x
                if _element_max_y > max_y:
                    max_y = _element_max_y
            else:
                if element.x < min_x:
                    min_x = element.x
                if element.y < min_y:
                    min_y = element.y

                _element_max_x = element.x + (element.width * element.scale)
                _element_max_y = element.y + (element.height * element.scale)
                if _element_max_x > max_x:
                    max_x = _element_max_x
                if _element_max_y > max_y:
                    max_y = _element_max_y
        return max_x - min_x, max_y - min_y

    @property
    def width(self):
        return self.size[0]

    @property
    def height(self):
        return self.size[1]
