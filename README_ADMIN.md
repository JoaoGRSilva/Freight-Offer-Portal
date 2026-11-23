# Etapa 1 — Administração e permissões

Copie os arquivos deste ZIP sobre o projeto original, mantendo data/, .env e .venv. Faça backup com o Flask desligado. O app.py foi reconstruído a partir do código enviado no chat; compare com sua versão local antes de substituir.

No CMD, com a venv ativa:

```
python
from services.user_repository import initialize_users, set_user_admin
initialize_users()
set_user_admin("SEU_EMAIL_CORPORATIVO", True)
exit()
python app.py
```

O retorno da promoção deve ser True. A migração mantém usuários e senhas existentes. Operadores antigos começam sem plantas; vincule pelo menu Administração. Não há migração de fretes: o filtro SQL usa dados_json.planta.codigo, já persistido. Fretes sem código não aparecem para operadores.

Teste com dois usuários e fretes de duas plantas: admin vê ambos; operador vê somente sua planta nas três listas; URL de detalhe e POST de outra planta retornam 403; dashboard/admin retornam 403; operador sem planta vê lista vazia. Verifique cadastro, edição, desativação e login. Teste também as negociações existentes com admin e operador autorizado.

Limitações: upload e limpeza global exclusivos do admin nesta etapa, pois o ETL identifica planta pelo nome do arquivo, que pode ser alterado. Envio de propostas na Home desativado (simulação antiga não é segura); negociação interna permanece. Antes de liberar acesso externo, revisar campos comerciais exibidos e elegibilidade de ofertas. ANTT, ANP e parâmetros ainda não implementados. CSRF aplicado aos formulários administrativos; revisar proteção CSRF das APIs operacionais existentes antes de produção. Testes de escopo SQLite e compilação realizados; Flask não disponível no ambiente de geração, portanto integração completa precisa ser testada localmente.
