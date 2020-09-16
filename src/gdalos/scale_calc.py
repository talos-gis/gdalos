import math


def calc_dot_pitch(screen_diagonal_inches=24, screen_width_pixels=1920, screen_height_pixels=1080):
    inches_to_meters = 0.0254
    screen_diagonal_meters = screen_diagonal_inches * inches_to_meters

    # screen_diagonal_meters**2 = (screen_width_pixels*x)**2 + (screen_height_pixels*x)**2
    # screen_diagonal_meters**2 = (screen_width_pixels**2 + screen_height_pixels**2) * x**2
    # screen_width_meters = x * screen_width_pixels
    x = math.sqrt(screen_diagonal_meters ** 2 / (screen_width_pixels ** 2 + screen_height_pixels ** 2))
    return x


def calc_scale(dot_pitch, pixels_at_zoom0=256, zoom=10, earth_r=6378137):
    pixels_at_zoom = pixels_at_zoom0 * (2 ** zoom)
    perimeter = 2 * math.pi * earth_r
    scale = perimeter / (pixels_at_zoom * dot_pitch)
    return scale


if __name__ == '__main__':
    web_mercator = True
    pixels = 256 if web_mercator else 512
    map_scale = round(calc_scale(dot_pitch=calc_dot_pitch(24, 1920, 1080), zoom=10, pixels_at_zoom0=pixels))
    print(map_scale)
