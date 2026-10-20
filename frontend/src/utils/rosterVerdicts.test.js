import { describe, it, expect } from 'vitest'
import {
  associatedPlayerIds,
  buildVerdictPayload,
  confirmLabel,
  detachmentBlockReasons,
  emptyVerdicts,
  groupByTeam,
  hasVerdict,
  unresolvedRows,
} from './rosterVerdicts'

const ROWS = [{ name: 'Ronald Holland II' }, { name: 'New Guy' }]

describe('rosterVerdicts -- aucun choix par défaut', () => {
  it('part de verdicts vides pour chaque ligne', () => {
    expect(emptyVerdicts(ROWS)).toEqual({
      'Ronald Holland II': { kind: null, playerId: null },
      'New Guy': { kind: null, playerId: null },
    })
  })

  it("toutes les lignes sont sans verdict au départ", () => {
    expect(unresolvedRows(ROWS, emptyVerdicts(ROWS))).toHaveLength(2)
  })
})

describe('rosterVerdicts -- ce qui compte comme un verdict', () => {
  it('« recrue » est un verdict', () => {
    expect(hasVerdict({ kind: 'recruit', playerId: null })).toBe(true)
  })
  it("« même joueur » SANS joueur choisi n'est pas un verdict", () => {
    expect(hasVerdict({ kind: 'same_player', playerId: null })).toBe(false)
  })
  it('« même joueur » avec un joueur choisi est un verdict', () => {
    expect(hasVerdict({ kind: 'same_player', playerId: 12 })).toBe(true)
  })
  it("un verdict vide ou absent n'est pas un verdict", () => {
    expect(hasVerdict({ kind: null, playerId: null })).toBe(false)
    expect(hasVerdict(undefined)).toBe(false)
  })
})

describe('rosterVerdicts -- ce que les verdicts autorisent', () => {
  it('les joueurs associés sont recensés (ils ne sont plus détachables)', () => {
    const verdicts = {
      'Ronald Holland II': { kind: 'same_player', playerId: 7 },
      'New Guy': { kind: 'recruit', playerId: null },
    }
    expect([...associatedPlayerIds(verdicts)]).toEqual([7])
  })

  it("une association sans joueur ne désigne personne", () => {
    expect(associatedPlayerIds({ x: { kind: 'same_player', playerId: null } }).size).toBe(0)
  })

  it('le détachement est possible sans ligne sans verdict ni erreur', () => {
    expect(detachmentBlockReasons({ unresolvedCount: 0, errorCount: 0 })).toEqual([])
  })

  it('les deux causes de blocage se cumulent et sont écrites', () => {
    const reasons = detachmentBlockReasons({ unresolvedCount: 2, errorCount: 3 })
    expect(reasons).toHaveLength(2)
    expect(reasons[0]).toContain('2 ligne(s) du fichier sans correspondance')
    expect(reasons[1]).toContain('3 ligne(s) du fichier sont en erreur')
  })
})

describe('rosterVerdicts -- corps envoyé au serveur', () => {
  it('ne contient que les lignes tranchées, au format attendu par le serveur', () => {
    const verdicts = {
      'Ronald Holland II': { kind: 'same_player', playerId: 7 },
      'New Guy': { kind: null, playerId: null },
    }
    expect(buildVerdictPayload(ROWS, verdicts)).toEqual([
      { file_name: 'Ronald Holland II', verdict: 'same_player', player_id: 7 },
    ])
  })

  it('une recrue ne porte aucun joueur', () => {
    const verdicts = { 'New Guy': { kind: 'recruit', playerId: null } }
    expect(buildVerdictPayload([{ name: 'New Guy' }], verdicts)).toEqual([{ file_name: 'New Guy', verdict: 'recruit' }])
  })

  it("rien n'est envoyé quand aucune ligne n'est tranchée", () => {
    expect(buildVerdictPayload(ROWS, emptyVerdicts(ROWS))).toEqual([])
  })
})

describe('rosterVerdicts -- libellé du bouton de confirmation', () => {
  it('« Confirmer l\'import » quand rien n\'est coché', () => {
    expect(confirmLabel(0)).toBe("Confirmer l'import")
  })
  it('annonce le nombre, au singulier puis au pluriel', () => {
    expect(confirmLabel(1)).toBe('Confirmer et détacher 1 joueur')
    expect(confirmLabel(72)).toBe('Confirmer et détacher 72 joueurs')
  })
})

describe('rosterVerdicts -- regroupement par équipe', () => {
  it('regroupe et trie par équipe puis par nom', () => {
    const players = [
      { id: 1, name: 'Zed', team_abbreviation: 'LAL' },
      { id: 2, name: 'Abe', team_abbreviation: 'BOS' },
      { id: 3, name: 'Bob', team_abbreviation: 'LAL' },
    ]
    const groups = groupByTeam(players)
    expect(groups.map((g) => g.team)).toEqual(['BOS', 'LAL'])
    expect(groups[1].players.map((p) => p.name)).toEqual(['Bob', 'Zed'])
  })
})
