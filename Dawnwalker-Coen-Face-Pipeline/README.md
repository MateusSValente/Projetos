# Dawnwalker — Coen Facial Geometry Test Pipeline

Pipeline conservador para testar alterações 3D no rosto do Coen sem recook completo da cabeça.

## Estado confirmado

No build atual, o caminho mais seguro é **preservar a serialização vanilla inteira e alterar somente o position buffer do LOD0**. O round-trip vanilla já passou por extração/importação e um no-op cirúrgico foi empacotado e abriu em gameplay.

O objetivo deste projeto é evitar o caminho frágil `UEMODEL -> Blender -> FBX -> recook completo` e usar:

```text
vanilla .uexp
+ posições vanilla exportadas do Blender
+ posições editadas exportadas do Blender
-> ajuste automático de espaço de coordenadas
-> patch SOMENTE dos bytes de posição
-> .uexp modificado
-> pipeline de empacotamento já validado localmente
```

## Por que este caminho

Ele mantém intactos:

- DNA/AssetUserData;
- bones/weights;
- material sections;
- morph metadata;
- normals/tangents já serializados;
- referências e estrutura do asset;
- todo byte fora do position buffer.

## Arquivos que NÃO entram no Git

Não publique assets do jogo, AES, `.uasset/.uexp`, `.pak/.ucas/.utoc`, DNA ou arquivos de mods de terceiros. O `.gitignore` deste projeto bloqueia esses tipos por padrão.

## Uso

### 1. Exportar posições vanilla do Blender

Abra o Blender com o head vanilla já importado e execute:

```bash
blender --background arquivo_vanilla.blend --python tools/export_vertex_positions.py -- --object NOME_DO_OBJETO --out vanilla_positions.csv
```

Ou rode o script pelo Text Editor do Blender.

### 2. Exportar a versão editada

Sem alterar topologia, ordem de vértices ou contagem:

```bash
blender --background arquivo_editado.blend --python tools/export_vertex_positions.py -- --object NOME_DO_OBJETO --out edited_positions.csv
```

### 3. Criar `manifest.local.json`

Copie `config/manifest.example.json` e preencha os valores já descobertos no pipeline local, principalmente offset/stride/formato do position buffer e SHA-256 do `.uexp` vanilla.

### 4. Gerar o `.uexp` de teste

```bash
python tools/patch_positions_surgical.py \
  --manifest manifest.local.json \
  --base SK_HMA_Coen_Head_A.uexp \
  --vanilla-csv vanilla_positions.csv \
  --edited-csv edited_positions.csv \
  --out SK_HMA_Coen_Head_A_TEST.uexp \
  --report patch_report.json
```

O script aborta se:

- SHA-256 do base não bater;
- contagem de vértices não bater;
- o ajuste de coordenadas vanilla -> game tiver erro alto;
- qualquer byte fora das posições previstas mudar;
- houver NaN/Inf.

### 5. Empacotar

Use **o mesmo pipeline local de retoc/payload que já produziu o vanilla no-op funcional**. Troque somente o `.uexp` pelo arquivo gerado acima. Não faça recook completo.

## Gate de teste no jogo

Primeiro teste deve alterar pouquíssimos vértices e pouca distância. Validar, nesta ordem:

1. jogo abre e save carrega;
2. cabeça aparece sem deformação explosiva;
3. câmera próxima/frontal/3-4;
4. lip sync;
5. expressões faciais;
6. piscada/olhos;
7. transformação vampírica;
8. cutscene curta;
9. retorno ao humano.

Se qualquer etapa falhar, rollback para o no-op conhecido e não aumentar o delta.

## Regra principal

**Não mudar topologia. Não reordenar vértices. Não recookar a cabeça inteira enquanto o patch de posições for suficiente.**
