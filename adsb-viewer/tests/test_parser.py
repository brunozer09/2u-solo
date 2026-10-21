import unittest

from src.parser import parse_line

class TestParseLine(unittest.TestCase):
    def test_linha_completa_valida(self):
        r = parse_line("adsb:e49c07,-22.547623,-46.248067,18000,370.4")
        self.assertIsNotNone(r)
        self.assertEqual(r.icao, "e49c07")
        self.assertAlmostEqual(r.latitude, -22.547623)
        self.assertAlmostEqual(r.longitude, -46.248067)
        self.assertAlmostEqual(r.altitude, 18000.0)
        self.assertAlmostEqual(r.air_speed, 370.4)

    def test_campos_none_viram_ausentes(self):
        r = parse_line("adsb:e49c07,None,None,18100,370.3")
        self.assertIsNotNone(r)
        self.assertEqual(r.icao, "e49c07")
        self.assertIsNone(r.latitude)
        self.assertIsNone(r.longitude)
        self.assertAlmostEqual(r.altitude, 18100.0)
        self.assertAlmostEqual(r.air_speed, 370.3)

    def test_linha_de_log_e_ignorada(self):
        for prefixo in ("[LOG]", "[WARN]", "[ERROR]", "[DEBUG]"):
            with self.subTest(prefixo=prefixo):
                self.assertIsNone(parse_line(f"{prefixo} alguma mensagem qualquer"))

    def test_linha_sem_prefixo_adsb_e_ignorada(self):
        self.assertIsNone(parse_line("e49c07,-22.5,-46.2,18000,370.4"))

    def test_linha_vazia_e_ignorada(self):
        self.assertIsNone(parse_line(""))
        self.assertIsNone(parse_line("   "))

    def test_numero_errado_de_campos_e_ignorado(self):
        self.assertIsNone(parse_line("adsb:e49c07,-22.5,-46.2,18000"))
        self.assertIsNone(parse_line("adsb:e49c07,-22.5,-46.2,18000,370.4,extra"))

    def test_icao_ausente_e_ignorado(self):
        self.assertIsNone(parse_line("adsb:,-22.5,-46.2,18000,370.4"))
        self.assertIsNone(parse_line("adsb:None,-22.5,-46.2,18000,370.4"))

    def test_valor_numerico_invalido_vira_ausente_mas_linha_e_aceita(self):
        r = parse_line("adsb:e49c07,abc,-46.2,18000,370.4")
        self.assertIsNotNone(r)
        self.assertIsNone(r.latitude)
        self.assertAlmostEqual(r.longitude, -46.2)

    def test_espacos_em_volta_dos_campos_sao_tolerados(self):
        r = parse_line("adsb: e49c07 , -22.5 , -46.2 , 18000 , 370.4 ")
        self.assertIsNotNone(r)
        self.assertEqual(r.icao, "e49c07")
        self.assertAlmostEqual(r.latitude, -22.5)


if __name__ == "__main__":
    unittest.main()
