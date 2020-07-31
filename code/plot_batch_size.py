import utilities_train as utrain
import utilities_figures as ufig
import utilities_various as uvar
import os

if __name__ == '__main__':

    batch_sizes = [1, 2, 5, 50, 512]
    ids = []
    for _, val in enumerate(batch_sizes):
        for i in range(3):
            ids.append('batch_size_' + str(val) + '_ID07_32h07m_' + str(i))
            ids.append('batch_size_' + str(val) + '_ID07_35h15m_' + str(i))
            ids.append('batch_size_' + str(val) + '_ID07_38h22m_' + str(i))
        uvar.print_params(ids[-1])
        print('---------------------------------------------')

    ufig.plot_multi_boxplots(ids=ids, x='batch_size', y='correlation', hue='brain_state',
                             save_name='batch_size')
    ufig.mean_weights(ids=ids, save_name='batch_size', hidden=False, diagonal=False)
