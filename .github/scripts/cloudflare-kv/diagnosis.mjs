/** Project actionable database errors without echoing request data or secrets. */
export function failureDiagnosis(error) {
  const text=String(error??'');
  const patterns=[
    ['missing_table',/no such table:\s*([A-Za-z_][A-Za-z0-9_]{0,63})/i],
    ['missing_column',/no such column:\s*([A-Za-z_][A-Za-z0-9_.]{0,63})/i],
    ['missing_function',/no such function:\s*([A-Za-z_][A-Za-z0-9_]{0,63})/i],
    ['unknown_insert_column',/has no column named\s+([A-Za-z_][A-Za-z0-9_]{0,63})/i],
    ['not_null',/NOT NULL constraint failed:\s*([A-Za-z_][A-Za-z0-9_.]{0,63})/i],
  ];
  for(const [category,pattern] of patterns){const m=text.match(pattern);if(m)return{category,schema_identifier:m[1]};}
  for(const [pattern,category] of [
    [/too many sql variables/i,'parameter_limit'],[/syntax error/i,'syntax_error'],
    [/datatype mismatch/i,'datatype'],[/D1_TYPE_ERROR|not supported for type/i,'bind_type'],
    [/wrong number of arguments/i,'function_arity'],[/foreign key constraint/i,'foreign_key'],
    [/unique constraint/i,'unique'],[/database is locked/i,'locked'],
    [/timeout|abort/i,'timeout'],[/D1|SQLITE/i,'database_unclassified'],
  ])if(pattern.test(text))return{category};
  return{category:'unclassified'};
}
