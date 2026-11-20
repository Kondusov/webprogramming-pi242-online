
let congratulation =  document.getElementById('congratulation');
let table = document.querySelector('table');
table.addEventListener('click', step);
let combinations = [
    [1,2,3], [4,5,6],[7,8,9],
    [1,4,7], [2,5,8],[3,6,9],
    [1,5,9], [3,5,7]
];
// let mainUser = 
// let secondUser = 
let switcher = 'X';
let currentCombinationsX = [];
let currentCombinationsO = [];
function step(event){
        if(event.target.textContent != ""){}
        else{
        //console.log(event);
        //console.log(event.target.getAttribute('id'));
        if(switcher=='O'){
            currentCombinationsO.push(Number(event.target.getAttribute('id')));
        }else{
            currentCombinationsX.push(Number(event.target.getAttribute('id')));
        }

        for(i=0; i<combinations.length; i++){
            // Проверка: все ли элементы currentCombinations есть в combinations?
            let counterX = 0;
            let counterO = 0;
            for(b=0; b<combinations[i].length; b++){
                if(switcher =='O'){currentCombinations=currentCombinationsO}
                else{currentCombinations=currentCombinationsX}

                //console.log(currentCombinations);
            console.log(combinations[i][b]);
                if(combinations[i].includes(currentCombinations[b])){
                    if(switcher== 'O'){
                        counterO++;
                    }else{counterX++}
                }
                if(counterX == 3 || counterO == 3){
                    console.log('победа '+switcher)
                    congratulation.textContent = `Победил ${switcher}`;
                    //setTimeout(()=>location.reload(), 3000);
                }
            }
        }
        if(switcher != 'O'){
            event.target.textContent = "X";
            switcher = 'O';
        }else{
            event.target.textContent = "O";
            switcher ='X';
        }
    console.log('Набор Х: '+currentCombinationsX);
    console.log('Набор O: '+currentCombinationsO);
    }
}