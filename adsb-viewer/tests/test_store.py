import unittest

from src.parser import AtualizacaoAeronave
from src.store import AircraftStore


def _upd(icao, lat=None, lon=None, alt=None, spd=None, raw=""):
    return AtualizacaoAeronave(
        icao=icao, latitude=lat, longitude=lon, altitude=alt, air_speed=spd, raw=raw
    )


class TestAircraftStore(unittest.TestCase):
    def test_upsert_cria_nova_aeronave(self):
        store = AircraftStore()
        store.upsert(_upd("e49c07", alt=18000, spd=370.3), agora=100.0)
        snap = store.snapshot(agora=100.0)
        self.assertEqual(len(snap), 1)
        aero = snap[0]
        self.assertEqual(aero["icao"], "e49c07")
        self.assertIsNone(aero["latitude"])
        self.assertEqual(aero["altitude"], 18000)

    def test_upsert_preserva_campos_nao_enviados(self):
        store = AircraftStore()
        store.upsert(_upd("e49c07", alt=18000, spd=370.3), agora=100.0)
        store.upsert(_upd("e49c07", lat=-22.5, lon=-46.2), agora=101.0)
        aero = store.snapshot(agora=101.0)[0]
        # posicao chegou na segunda mensagem, altitude/velocidade da primeira
        # devem continuar presentes (upsert, nao substituicao total)
        self.assertEqual(aero["latitude"], -22.5)
        self.assertEqual(aero["longitude"], -46.2)
        self.assertEqual(aero["altitude"], 18000)
        self.assertEqual(aero["air_speed"], 370.3)

    def test_upsert_de_icaos_diferentes_nao_se_confundem(self):
        store = AircraftStore()
        store.upsert(_upd("e49c07", alt=18000), agora=100.0)
        store.upsert(_upd("e4a5b4", alt=21050), agora=100.0)
        snap = {a["icao"]: a for a in store.snapshot(agora=100.0)}
        self.assertEqual(set(snap.keys()), {"e49c07", "e4a5b4"})
        self.assertEqual(snap["e49c07"]["altitude"], 18000)
        self.assertEqual(snap["e4a5b4"]["altitude"], 21050)

    def test_marca_como_stale_apos_o_limiar(self):
        store = AircraftStore(stale_after=30.0, remove_after=300.0)
        store.upsert(_upd("e49c07", alt=18000), agora=100.0)
        self.assertFalse(store.snapshot(agora=110.0)[0]["stale"])
        self.assertTrue(store.snapshot(agora=131.0)[0]["stale"])

    def test_remove_apos_o_limiar_de_expiracao(self):
        store = AircraftStore(stale_after=30.0, remove_after=300.0)
        store.upsert(_upd("e49c07", alt=18000), agora=100.0)
        self.assertEqual(len(store.snapshot(agora=399.0)), 1)
        self.assertEqual(len(store.snapshot(agora=401.0)), 0)

    def test_remove_after_none_nunca_expira(self):
        store = AircraftStore(stale_after=5.0, remove_after=None)
        store.upsert(_upd("e49c07", alt=18000), agora=0.0)
        self.assertEqual(len(store.snapshot(agora=10_000_000.0)), 1)

    def test_remove_after_menor_que_stale_after_e_invalido(self):
        with self.assertRaises(ValueError):
            AircraftStore(stale_after=60.0, remove_after=10.0)


if __name__ == "__main__":
    unittest.main()
