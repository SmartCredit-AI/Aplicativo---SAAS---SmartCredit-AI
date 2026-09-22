# Regras e Instruções do SmartCredit-AI

## Regra de Ouro: Sincronização Obrigatória Pós-Atualização
Sempre que forem feitas alterações, implementações ou correções de código no projeto:

1. **GitHub**:
   - Executar `git add .`
   - Realizar commit com mensagem clara (`git commit -m "..."`)
   - Fazer push imediato para o repositório remoto (`git push origin main`)

2. **Vercel**:
   - O projeto possui `vercel.json` e integração com a branch `main`. O push para o GitHub aciona automaticamente a publicação/deploy em produção na Vercel.
   - Sempre certificar que `vercel.json` e a estrutura estejam íntegras para o deploy.

3. **Supabase**:
   - Projeto vinculado: `ozlrcqareyyjqjkqiniu`.
   - Se houver alterações em banco de dados ou migrações SQL (`supabase/migrations/`), executar:
     ```cmd
     cmd /c "npx supabase db push"
     ```
   - Validar sincronia com:
     ```cmd
     cmd /c "npx supabase migration list"
     ```
