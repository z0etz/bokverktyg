"""
Delat tillstånd för avbrytning av flöden.
"""
_avbryt_flaggor = {}


def satt_avbryt(projekt_id):
    _avbryt_flaggor[projekt_id] = True


def rensa_avbryt(projekt_id):
    _avbryt_flaggor[projekt_id] = False


def ar_avbruten(projekt_id):
    return _avbryt_flaggor.get(projekt_id, False)