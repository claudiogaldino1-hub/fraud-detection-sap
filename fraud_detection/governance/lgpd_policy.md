# Política de Privacidade e LGPD — Sistema de Detecção de Fraudes P2P

**Versão:** 1.0  
**Data:** 2024-01-01  
**Responsável:** DPO (Data Protection Officer)

---

## 1. Contexto e Finalidade

Este sistema processa dados sintéticos (fictícios) para fins de **desenvolvimento, treinamento e demonstração** de algoritmos de detecção de anomalias financeiras no fluxo Procure to Pay (P2P) baseado em tabelas SAP.

**Em ambiente de produção**, todos os dados processados são dados pessoais e/ou sensíveis de fornecedores e colaboradores, regulados pela Lei Geral de Proteção de Dados (LGPD — Lei n.º 13.709/2018).

---

## 2. Base Legal de Tratamento (Art. 7º LGPD)

| Categoria de Dado | Base Legal |
|---|---|
| Nome e CNPJ de fornecedor | Cumprimento de obrigação legal (art. 7º, II) |
| Dados bancários de fornecedor | Execução de contrato (art. 7º, V) |
| Dados de usuário SAP (USNAM/ERNAM) | Legítimo interesse — controle interno (art. 7º, IX) |
| Logs de auditoria | Cumprimento de obrigação legal (art. 7º, II) |

---

## 3. Sensibilidade dos Campos

| Campo SAP | Classificação | Retenção |
|---|---|---|
| STCD1 (CNPJ/CPF) | Restrito | 5 anos após encerramento do contrato |
| BANKL / BANKN | Restrito | 5 anos após o último pagamento |
| ERNAM / USNAM | Confidencial | 2 anos |
| SMTP_ADDR / TELF1 | Restrito | 1 ano após inatividade |
| DMBTR / WRBTR | Confidencial | 10 anos (obrigação fiscal) |

---

## 4. Medidas de Segurança Implementadas

- **Pseudonimização:** Identificadores de usuário substituídos por hashes em datasets de treino.
- **RBAC:** Acesso segmentado por perfil — analista, gestor, auditor.
- **Audit Trail:** Log imutável com cadeia de hashes (SHA-256) para rastreabilidade.
- **Minimização:** Apenas campos necessários para cada perfil são expostos via API.
- **Criptografia em repouso:** Arquivos Parquet armazenados com AES-256 em produção.
- **TLS 1.3:** Todas as comunicações API criptografadas.

---

## 5. Direitos dos Titulares (Art. 18 LGPD)

Fornecedores e colaboradores têm direito a:

- **Acesso** — Solicitar quais dados estão sendo processados.
- **Retificação** — Corrigir dados inexatos.
- **Eliminação** — Solicitar exclusão de dados desnecessários.
- **Portabilidade** — Receber dados em formato estruturado.
- **Oposição** — Contestar tratamento baseado em legítimo interesse.

**Canal:** dpo@empresa.com.br  
**Prazo de resposta:** 15 dias úteis.

---

## 6. Transferência Internacional

Dados **não** são transferidos para servidores fora do Brasil sem:
1. Garantias de nível adequado de proteção (art. 33 LGPD).
2. Cláusulas contratuais padrão.
3. Consentimento explícito do titular (quando aplicável).

**Nota:** A Claude API (Anthropic) recebe apenas narrativas de alerta **sem identificadores pessoais** — apenas scores, tipos de fraude e valores agregados. O prompt enviado é auditado e não contém CNPJ, CPF, dados bancários ou nomes de pessoas físicas.

---

## 7. Dados Fictícios — Disclaimers

- Todos os CNPJs, nomes, endereços e dados bancários gerados neste sistema são **completamente fictícios**.
- Qualquer semelhança com dados reais é mera coincidência.
- O sistema **não deve ser implantado com dados reais** sem revisão completa desta política e aprovação do DPO.

---

## 8. Incidentes de Segurança

Em caso de violação de dados:
1. Notificar a ANPD em até **72 horas** (art. 48 LGPD).
2. Notificar os titulares afetados com detalhes do incidente.
3. Registrar no AUDIT_LOG.json com action = `SECURITY_INCIDENT`.

---

## 9. Revisão desta Política

Esta política deve ser revisada:
- Anualmente.
- Após qualquer incidente de segurança.
- Quando houver mudança significativa no tratamento de dados.

---

*Documento gerado automaticamente. Deve ser revisado pelo DPO antes de uso em produção.*
