#!/bin/bash
DIR='./env/game/gameplay'

yq '.' \
${DIR}/grooves.yaml \
${DIR}/commanders.yaml \
${DIR}/terrains.yaml \
${DIR}/commanders.yaml \
${DIR}/verbs.yaml \
${DIR}/units/*.yaml \
${DIR}/structures/*.yaml \
| jq -s \
'def deepmerge(a;b):
  reduce b[] as $item (a;
  reduce ($item | keys_unsorted[]) as $key (.;
  $item[$key] as $val | ($val | type) as $type | .[$key] = if ($type == "object") then
  deepmerge({}; [if .[$key] == null then {} else .[$key] end, $val])
  elif ($type == "array") then
  (.[$key] + $val | unique)
  else $val end));
deepmerge({}; .)' | jq '{
    terrains: .terrains | map({(.id|tostring): . }) | add,
    grooves: .grooves | map({(.id|tostring): . }) | add,
    commanders: .commanders | map({(.id|tostring): . }) | add,
    verbs: .verbs | map({(.id|tostring): . }) | add,
    weapons: .weapons | map({(.id|tostring): . }) | add,
    unitClasses: .unitClasses | map({(.id|tostring): . }) | add
}' > ./env/game/wg_2.0.json