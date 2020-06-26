from game import *
import torch
from utils import *
import tetrimino

'''
heuristics are from https://codemyroad.wordpress.com/2013/04/14/tetris-ai-the-near-perfect-player/
'''

class AIGame:
    def __init__(self, game: Game = None):
        if game is not None:
            self.game = game
        else:
            self.game = Game()
        self.lines = self.game.totalLinesCleared
        self.prevLines = self.lines

    def copy(self):
        ans = AIGame(self.game.copy())
        ans.lines = self.lines
        ans.prevLines = ans.lines
        return ans

    def getLegalActions(self):
        return actions + [None]

    def move(self, action):
        if action is None:
            return self.copy()
        else:
            ans = self.copy()
            ans.game.aiUpdate([action])
            return ans
    
    def toTensor(self):
        def oneHotPiece(piece):
            if piece is None:
                return [1,0]
            else:
                return [0,1]
        game = self.game.copy()
        if game.currentTetrimino is not None:
            for p in game.getTetriminoActivePositions():
                game.setPieceAt(game.currentTetrimino, p)
        grid = game.grid
        grid = grid[:game.lastVisibleRow+1]
        grid = [[oneHotPiece(piece) for piece in row] for row in grid]
        grid = torch.tensor(grid).to(device)
        grid = torch.flatten(grid)
        
        def oneHotTetrimino(t, hold=False):
            if t is None and hold:
                return [0,0,0,0,0,0,0,1]
            else:
                pieceType = t.pieceType
                index = tetrimino.types.index(pieceType)
                length = 8 if hold else 7
                ans = [0 for _ in range(length)]
                ans[index] = 1
                return ans
        hold = self.game.holdTetrimino
        hold = oneHotTetrimino(hold, hold=True)
        hold = torch.tensor(hold).to(device)

        nexts = self.game.getUpcomingTetriminos()
        nexts = [oneHotTetrimino(t) for t in nexts]
        nexts = torch.tensor(nexts).to(device)
        nexts = torch.flatten(nexts)

        level = self.game.level
        level = torch.tensor([level]).to(device)
        
        ans = torch.cat([grid, hold, nexts, level], dim=0)
        ans = ans.unsqueeze(dim=0) # batch

        ans = ans.to(torch.float)

        return ans

    def isDead(self):
        return self.game.dead

    def score(self):
        return self.game.score * self.game.frameRate
    
    def heuristicScore(self):
        gridT = [[None for y in range(self.game.lastVisibleRow+1)] for x in range(self.game.width)]
        for x in range(self.game.width):
            for y in range(self.game.lastVisibleRow+1):
                gridT[x][y] = self.game.grid[y][x]
        
        # aggregate height
        def height(col):
            indices = (i for i in range(self.game.lastVisibleRow+1))
            activeIndices = filter(lambda row: gridT[col][row] is not None, indices)
            return max(activeIndices,default=0)
        heights = tuple(height(col) for col in range(self.game.width))
        aggregateHeight = sum(heights)

        # porosity
        def isHole(x, y):
            if y <= self.game.lastVisibleRow-1:
                return gridT[x][y] is None and gridT[x][y+1] is not None
            else:
                return False
        
        holes = 0
        for x in range(self.game.width):
            for y in range(self.game.lastVisibleRow+1):
                if isHole(x,y):
                    holes += 1
        
        # bumpiness
        bumpiness = 0
        for h1, h2 in zip(heights,heights[1:]):
            bumpiness += abs(h1-h2)
        
        # lines just cleared
        clears = self.lines - self.prevLines
        

        # completedLines = game.
        a = -0.510066
        b = 0.760666
        c = -0.35663
        d = -0.184483
        return a * aggregateHeight + b * clears + c * holes + d * bumpiness

    def __eq__(self, other):
        return isinstance(other, AIGame) and self.game == other.game

    def __hash__(self):
        return hash(self.game)


class HighLevelAIGame(AIGame):
    '''Instead of doing individual inputs, a move is a (position, rotation) pair
    where doing the move hard drops a piece at that x position with that rotation
    '''
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    
    def getLegalActions(self):
        positions = tuple(range(-5,6))
        rotations = tuple(range(4))
        ans = [(p, r) for p in positions for r in rotations]
        # if self.game.canHold and self.game.canMove():
        #     ans.append(HOLD)
        return ans
        
    
    def move(self, action):
        assert action in self.getLegalActions()
        ans = self.copy()
        game = ans.game
        ans.prevLines = ans.lines
        for inputsHeld in self.generateInputs(action):
            game.update(inputsHeld)
        ans.lines = game.totalLinesCleared
        return ans
    
    def generateInputs(self, action):
        assert action in self.getLegalActions()
        if action == HOLD:
            return [[HOLD]]
        ans = self.copy()
        game = ans.game
        inputs = []
        shifts = []
        rotations = []
        while not ans.game.canMove():
            game.update()
            inputs.append([])
        position, rotation = action
        if rotation == 1:
            rotations.append([RCW])
        elif rotation == 2:
            rotations.append([RCW])
            rotations.append([])
            rotations.append([RCW])
        elif rotation == 3:
            rotations.append([RCCW])

        if position < 0:
            for _ in range(-position):
                shifts.append([LEFT])
                shifts.append([])
        elif position > 0:
            for _ in range(position):
                shifts.append([RIGHT])
                shifts.append([])

        # rotShifts = []        
        # for (rotation, shift) in zip(rotations, shifts):
        #     rotations.pop(0)
        #     shifts.pop(0)
        #     rotShifts.append(rotation + shift)
        
        # inputs += rotShifts
        
        inputs += rotations
        inputs += shifts

        inputs.append([HARD])
        inputs.append([])
        return inputs
