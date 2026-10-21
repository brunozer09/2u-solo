import copy
import json
import tempfile
import unittest
from pathlib import Path

from src.telemetry_schema import CAMINHO_PADRAO, SchemaTelemetria, carregar_schema


def _base():
    return {
        "campos": [
            {"chave": "a", "rotulo": "A", "unidade": "m", "casas": 1},
            {"chave": "b", "rotulo": "B", "tipo": "int"},
            {"chave": "taxa", "rotulo": "Taxa", "derivado": True},
        ],
        "layout": {
            "resumo": ["a", {"campo": "b", "casas": 0}],
            "paineis_laterais": [{"titulo": "P", "campos": ["a", "taxa"]}],
            "faixa_sensores": [{"titulo": "S", "campos": ["a", "b"]}],
            "graficos": [{"id": "g1", "series": [{"chave": "a"}], "destaque": ["a"]}],
        },
    }


class TestSchema(unittest.TestCase):
    def test_schema_do_projeto_e_valido(self):
        schema = carregar_schema(CAMINHO_PADRAO)
        self.assertEqual(len(schema.chaves_serial), 20)
        self.assertEqual(schema.chaves_serial[0], "rssi")
        self.assertEqual(schema.chaves_serial[-1], "checksum")
        self.assertNotIn("taxa_hz", schema.chaves_serial)  # derivado: nao vem da serial

    def test_ordem_e_derivados(self):
        schema = SchemaTelemetria(_base())
        self.assertEqual(schema.chaves_serial, ("a", "b"))
        self.assertEqual(schema.campo("b").tipo, "int")
        self.assertTrue(schema.campo("taxa").derivado)

    def test_chave_duplicada(self):
        d = _base()
        d["campos"].append({"chave": "a"})
        with self.assertRaisesRegex(ValueError, "duplicada"):
            SchemaTelemetria(d)

    def test_chave_reservada_e_invalida(self):
        for chave in ("t_pc_iso", "seq", "Maiuscula", "1x", "com espaco"):
            d = _base()
            d["campos"].append({"chave": chave})
            with self.subTest(chave=chave), self.assertRaises(ValueError):
                SchemaTelemetria(d)

    def test_tipo_e_casas_invalidos(self):
        d = _base()
        d["campos"][0]["tipo"] = "complexo"
        with self.assertRaisesRegex(ValueError, "tipo invalido"):
            SchemaTelemetria(d)
        d = _base()
        d["campos"][0]["casas"] = -1
        with self.assertRaisesRegex(ValueError, "casas"):
            SchemaTelemetria(d)

    def test_layout_referenciando_campo_inexistente(self):
        for onde in ("resumo", "paineis_laterais", "faixa_sensores", "graficos"):
            d = copy.deepcopy(_base())
            if onde == "resumo":
                d["layout"]["resumo"].append("fantasma")
            elif onde == "graficos":
                d["layout"]["graficos"][0]["series"].append({"chave": "fantasma"})
            else:
                d["layout"][onde][0]["campos"].append("fantasma")
            with self.subTest(onde=onde), self.assertRaisesRegex(ValueError, "fantasma"):
                SchemaTelemetria(d)

    def test_nao_aceita_schema_sem_campos_serial(self):
        d = {"campos": [{"chave": "x", "derivado": True}]}
        with self.assertRaisesRegex(ValueError, "nenhum campo"):
            SchemaTelemetria(d)

    def test_arquivo_inexistente_e_json_invalido(self):
        with self.assertRaisesRegex(ValueError, "nao foi possivel ler"):
            carregar_schema(Path("/nao/existe.json"))
        with tempfile.TemporaryDirectory() as tmp:
            ruim = Path(tmp) / "ruim.json"
            ruim.write_text("{ nao e json", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "JSON invalido"):
                carregar_schema(ruim)

    def test_para_dict_e_serializavel(self):
        json.dumps(carregar_schema().para_dict())


if __name__ == "__main__":
    unittest.main()
