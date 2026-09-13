from scripts import seed_casos_exemplo as exemplos
from src.interface.backend.repository import Repository


def test_casos_de_exemplo_entram_com_os_pdfs_da_enter(tmp_path):
    database = tmp_path / "demo.db"
    resumo = exemplos.semear(database)
    assert [item["situacao"] for item in resumo] == ["criado", "criado"]
    repository = Repository(database)
    advogada = repository.get_user_by_email("advogada@demo.local")
    casos = {case["case_number"]: case for case in repository.list_cases(lawyer_id=advogada["id"])}
    assert set(casos) == {"0801234-56.2024.8.10.0001", "0654321-09.2024.8.04.0001"}
    documentos = repository.list_documents(casos["0801234-56.2024.8.10.0001"]["id"])
    assert len(documentos) == 7 and all(d["status"].startswith("COMPLETED") and d["page_count"] > 0 for d in documentos)
    tipos_caso2 = {d["declared_type"] for d in repository.list_documents(casos["0654321-09.2024.8.04.0001"]["id"])}
    assert "CONTRATO" not in tipos_caso2 and "EXTRATO" not in tipos_caso2
    assert all(repository.list_analyses(case["id"]) for case in casos.values()), "recomendação já calculada"
    assert [item["situacao"] for item in exemplos.semear(database)] == ["já existia", "já existia"]
    assert [item["situacao"] for item in exemplos.semear(database, reset=True)] == ["criado", "criado"]
    assert len(repository.list_cases(lawyer_id=advogada["id"])) == 2
