"""The pose library: ToeJam & Earl animation -> posed Rick/Morty frames (see puppet.py).

make(pose, who, facing, i) returns the i-th frame of that pose as an fx.Art.
"""
from puppet import Face, Legs, render

OPEN = Face(mouth="open")
OUCH = Face(mouth="open", eyes="shut")
SHUT = Face(eyes="shut")


def _alt(i, a, b):
    return a if i % 2 == 0 else b


def make(pose, who, facing, i):
    view = facing  # down / up / side ("right" -> side)
    if view == "right":
        view = "side"
    side = view == "side"

    if pose == "run":  # hi-tops: feet whirling, arms pumping
        if side:
            return render(who, "side", arms=_alt(i, (75, -45), (-45, 75)), legs=Legs("wheel", phase=i))
        return render(who, view, arms=_alt(i, (30, 8), (8, 30)), legs=Legs("blur", phase=i), bob=i % 2)
    if pose == "sneak":  # tiptoeing, knees bent, hands up
        if side:
            return render(who, "side", arms=_alt(i, (80,), (65,)), legs=Legs("crouch"), bob=2)
        return render(who, view, arms=_alt(i, (45, 35), (35, 45)), legs=Legs("crouch"), bob=1)
    if pose == "teeter":  # arms windmilling at the edge
        if side:
            return render(who, "side", arms=_alt(i, (155, 40), (40, 155)), legs=Legs("spread"), face=OPEN)
        return render(who, view, arms=_alt(i, (125, 55), (55, 125)), legs=Legs("stand"), face=OPEN)
    if pose == "fall":  # dropping down a hole: arms up, legs dangling
        if side:
            return render(who, "side", arms=_alt(i, (165, 145), (145, 165)), legs=Legs("dangle"), face=OPEN)
        return render(who, view, arms=_alt(i, (165, 150), (150, 165)), legs=Legs("dangle"), face=OPEN)
    if pose == "land":  # squash on impact
        return render(who, view, arms=(70,) if side else (70, 70), legs=Legs("spread"), squash=0.85)
    if pose == "pain":  # youch
        return render(who, view, arms=(110, 60) if side else (100, 100), legs=Legs("spread"), face=OUCH)
    if pose == "leap":
        return render(who, view, arms=(160, 120) if side else (160, 160), legs=Legs("tuck"), face=OPEN, bob=-2)
    if pose == "dive":  # head-first into the water
        if side:
            art = render(who, "side", arms=(175, 170), legs=Legs("stand"))
            from fx import Art
            img = art.img.rotate(-90, expand=True)
            return Art(img, img.width // 2, img.height - 1)
        return render(who, view, arms=(178, 178), legs=Legs("dangle"))
    if pose == "climb":  # hauling out of the water, seen from behind
        return render(who, "up", arms=_alt(i, (170, 120), (120, 170)), legs=Legs("walk", phase=i * 2 + 1))
    if pose == "throw":
        if side:
            return render(who, "side", arms=_alt(i, (-130,), (95,)), legs=Legs("walk", phase=1))
        return render(who, view, arms=_alt(i, (10, 165), (10, 70)), legs=Legs("stand"))
    if pose == "slingshot":
        return render(who, view, arms=(90, 80) if side else (55, 55), legs=Legs("spread"))
    if pose == "highfive":
        return render(who, view, arms=(160,) if side else _alt(i, (8, 165), (8, 145)), legs=Legs("stand"), face=OPEN)
    if pose == "covers":  # hands over ears
        return render(who, view, arms=(150,) if side else (152, 152), legs=Legs("stand"), face=SHUT)
    if pose == "read":
        return render(who, view, arms=(60,) if side else (28, 28), legs=Legs("stand"), prop="book")
    if pose == "cheer":  # extra life
        return render(who, view, arms=(170, 160) if side else (170, 170), legs=Legs("tuck"), face=OPEN, bob=-3)
    if pose == "hula":
        return render(who, view, arms=_alt(i, (95,), (60,)) if side else _alt(i, (100, 60), (60, 100)),
                      legs=Legs("walk", phase=i))
    if pose == "shield":  # tomatoes falling on your head
        return render(who, view, arms=(175,) if side else (172, 172), legs=Legs("stand"), face=SHUT)
    if pose == "swig":  # Rick's flask (in place of Earl dropping his pants)
        return render(who, view, arms=(150,) if side else (8, 150), legs=Legs("stand"), prop="flask")
    raise KeyError(pose)
