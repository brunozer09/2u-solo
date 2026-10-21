import math
import unittest

from src.telemetry import MAX_LINHAS_PACOTE, MontadorPacote, converter_valor, separar_valores
from src.telemetry_schema import carregar_schema

PACOTE_OK = [
    "Msg:-91,7.5,64",
    "Id:12",
    "Millis:456789",
    "Bat:7.41,152.3",
    "Pos:-23.2237,-45.9009,640.2",
    "Baro:931.2,660.1,22.4",
    "Acel:0.01,-0.02,0.99",
    "Giro:1.2,-0.4,0.3",
    "Checksum:1",
]


def _alimentar_todas(montador, linhas):
    pacotes, consumidas = [], []
    for linha in linhas:
        r = montador.alimentar(linha)
        consumidas.append(r.consumida)
        if r.pacote is not None:
            pacotes.append(r.pacote)
    return pacotes, consumidas


class TestConversao(unittest.TestCase):
    def test_separar_valores(self):
        self.assertEqual(separar_valores("1, 2 ,3"), ["1", "2", "3"])
        self.assertEqual(separar_valores("1 2 3"), ["1", "2", "3"])
        self.assertEqual(separar_valores("   "), [])

    def test_converter(self):
        self.assertEqual(converter_valor("12", "int"), 12)
        self.assertIsInstance(converter_valor("12.0", "int"), int)
        self.assertEqual(converter_valor("12.5", "int"), 12.5)  # nao perde dado
        self.assertAlmostEqual(converter_valor("-91.25", "float"), -91.25)
        self.assertEqual(converter_valor("A3", "texto"), "A3")

    def test_ausentes_e_invalidos_viram_none(self):
        for bruto in ("NaN", "nan", "None", "", "  ", "abc", "inf", "-inf", "1e999"):
            with self.subTest(bruto=bruto):
                self.assertIsNone(converter_valor(bruto, "float"))
        self.assertIsNone(converter_valor("NaN", "texto"))


class TestMontador(unittest.TestCase):
    def setUp(self):
        self.schema = carregar_schema()
        self.relogio = lambda: 1000.5
        self.m = MontadorPacote(self.schema, relogio=self.relogio)

    def test_pacote_completo(self):
        pacotes, consumidas = _alimentar_todas(self.m, PACOTE_OK)
        self.assertEqual(len(pacotes), 1)
        self.assertTrue(all(consumidas))
        p = pacotes[0]
        self.assertTrue(p.completo)
        self.assertEqual(p.campos["rssi"], -91)
        self.assertAlmostEqual(p.campos["snr"], 7.5)
        self.assertEqual(p.campos["size"], 64)
        self.assertEqual(p.campos["id"], "12")
        self.assertEqual(p.campos["millis"], 456789)
        self.assertAlmostEqual(p.campos["alt_baro"], 660.1)
        self.assertAlmostEqual(p.campos["gz"], 0.3)
        self.assertEqual(p.campos["checksum"], 1)
        self.assertEqual(list(p.campos), list(self.schema.chaves_serial))
        self.assertEqual(p.brutos[0], "-91")
        self.assertEqual(p.recebido_em, 1000.5)
        self.assertFalse(self.m.em_andamento)

    def test_nomes_dos_grupos_sao_ignorados(self):
        renomeado = [linha.split(":", 1)[0].lower() + ":" + linha.split(":", 1)[1] if i else linha
                     for i, linha in enumerate(PACOTE_OK)]
        renomeado[1] = "Identificador:12"
        renomeado[-1] = "Checksum:1"
        pacotes, _ = _alimentar_todas(self.m, renomeado)
        self.assertEqual(pacotes[0].campos["id"], "12")

    def test_linhas_fora_de_pacote_nao_sao_consumidas(self):
        for linha in ("adsb:e49c07,1,2,3,4", "[DEBUG] x", "RX", "", "lixo qualquer"):
            with self.subTest(linha=linha):
                self.assertFalse(self.m.alimentar(linha).consumida)

    def test_linhas_adsb_e_log_dentro_do_pacote_passam_adiante(self):
        linhas = PACOTE_OK[:4] + ["adsb:e49c07,-22.5,-46.2,18000,370.4", "[DEBUG] oi", "RX"] + PACOTE_OK[4:]
        pacotes, consumidas = _alimentar_todas(self.m, linhas)
        self.assertEqual(len(pacotes), 1)
        self.assertEqual(consumidas[4:7], [False, False, False])  # nao consumidas
        self.assertEqual(pacotes[0].campos["alt_gps"], 640.2)      # pacote integro

    def test_novo_msg_descarta_pacote_incompleto(self):
        pacotes, _ = _alimentar_todas(self.m, PACOTE_OK[:5] + PACOTE_OK)
        self.assertEqual(len(pacotes), 1)
        self.assertTrue(pacotes[0].completo)

    def test_pacote_curto_completa_com_ausentes(self):
        curto = PACOTE_OK[:6] + ["Checksum:1"]  # sem Acel/Giro
        pacotes, _ = _alimentar_todas(self.m, curto)
        p = pacotes[0]
        self.assertFalse(p.completo)
        self.assertIsNone(p.campos["gz"])
        self.assertEqual(p.brutos[-2], "NaN")
        self.assertEqual(len(p.brutos), 20)

    def test_valores_a_mais_sao_truncados(self):
        longo = PACOTE_OK[:-1] + ["Extra:9,9,9", "Checksum:1"]
        pacotes, _ = _alimentar_todas(self.m, longo)
        self.assertFalse(pacotes[0].completo)
        self.assertEqual(len(pacotes[0].campos), 20)

    def test_pacote_sem_checksum_e_descartado_apos_limite(self):
        self.m.alimentar("Msg:-91,7.5,64")
        for _ in range(MAX_LINHAS_PACOTE + 2):
            self.m.alimentar("Id:1")
        self.assertFalse(self.m.em_andamento)
        self.assertFalse(self.m.alimentar("Id:1").consumida)

    def test_valor_invalido_vira_none_sem_derrubar_o_pacote(self):
        linhas = list(PACOTE_OK)
        linhas[3] = "Bat:abc,152.3"
        pacotes, _ = _alimentar_todas(self.m, linhas)
        self.assertIsNone(pacotes[0].campos["vbat"])
        self.assertAlmostEqual(pacotes[0].campos["ibat"], 152.3)

    def test_para_dict_e_json_valido(self):
        import json
        pacotes, _ = _alimentar_todas(self.m, PACOTE_OK[:6] + ["Checksum:1"])
        d = pacotes[0].para_dict()
        texto = json.dumps(d, allow_nan=False)  # nao pode levantar (sem NaN)
        self.assertIn('"t_pc_iso"', texto)
        self.assertEqual(d["t_pc"], 1000.5)

    def test_dois_pacotes_seguidos(self):
        pacotes, _ = _alimentar_todas(self.m, PACOTE_OK + PACOTE_OK)
        self.assertEqual(len(pacotes), 2)


if __name__ == "__main__":
    unittest.main()
